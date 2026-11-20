"""The 'brain' of the project: plans the analysis and orchestrates the whole pipeline.

question -> schema -> entity hints -> PLAN -> for each step:
    generate SQL -> validate -> execute -> (repair loop on failure) -> answer
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Callable

from .answer_generator import generate_answer
from .database import get_connection
from .ollama_client import OllamaClient, OllamaError
from .query_executor import QueryResult, execute_query
from .schema_inspector import column_ownership_text, inspect_schema, schema_to_text
from .sql_generator import generate_sql
from .sql_repair import repair_sql
from .sql_validator import validate_sql

MAX_STEPS = 4

PLANNER_PROMPT = """You are a senior data analyst for NovaCart, an Indian e-commerce store selling Apple products.

Your task is to break the user's business question into a SHORT analysis plan. Each step must be independently answerable using exactly ONE MySQL 8 SELECT query against the provided database.

You are planning the investigation, NOT writing SQL.

==================================================
CORE RULES
==================================================

1. Use ONLY information available in the DATABASE SCHEMA.

2. Never create a step that requires data not present in the schema.
   Do not assume the database contains:
   - reviews
   - competitor prices
   - advertising spend
   - website traffic
   - inventory
   - customer satisfaction
   - any other unavailable data

3. For diagnostic / "why" questions:
   Create 3-4 steps maximum.
   Each step must investigate a DIFFERENT possible explanation.

   Useful diagnostic angles include:
   - baseline sales volume / ranking
   - monthly sales trend
   - price positioning
   - margin
   - discounts
   - cancelled orders / order-status mix
   - returns and return reasons
   - customer segment
   - acquisition channel
   - geographic performance
   - product launch date / selling availability

4. Step 1 MUST establish the baseline:
   How much did the target product sell, and how does that compare with relevant products?

5. Do not create separate steps when one SQL query can answer the question.

6. For simple factual questions, ranking questions, or "which X" questions:
   Use exactly ONE step.

   Example:
   "Which iPhone model sells the most?"

   Correct plan:
   1. Rank iPhone products by total units sold.

   Do NOT create:
   1. Find all iPhone products.
   2. Calculate their sales.
   3. Rank them.

7. For comparisons between two named entities:
   Use 1-2 steps.

8. For trend questions:
   Include a time-based analysis using the available date column.

9. For diagnostic questions, each step must have:
   - a clear analytical goal
   - a testable hypothesis

10. Do not assume that a hypothesis is true.
    The hypothesis is something the SQL analysis should test.

11. Respect product variants.
    For example:
    "iPhone 16 Pro" may correspond to several exact product_name values such as:
    "iPhone 16 Pro 128GB"
    "iPhone 16 Pro 256GB"

12. The database contains launch_date for products.
    A product launched late in the analysis period may naturally have lower total sales.
    Consider launch timing when it is relevant.

==================================================
BUSINESS DEFINITIONS
==================================================

Use these concepts when deciding what should be analyzed:

- A sale = an order_items row belonging to an order whose order_status <> 'Cancelled'.
- Units sold = SUM(order_items.quantity).
- Revenue = SUM(quantity * unit_price - item_discount).
- Margin per unit = products.selling_price - products.cost_price.
- Region = orders.shipping_state.
- Return rate = returned items / items belonging to Delivered orders.
- Monthly analysis should use orders.order_date.

==================================================
FEW-SHOT PLANNING EXAMPLES
==================================================

Example 1
USER QUESTION:
"Why did iPhone 14 128GB not sell much?"

GOOD PLAN:
1. Compare the target product's units sold with other iPhone products.
   Hypothesis: The product has unusually low sales volume compared with similar products.

2. Analyze the product's monthly units sold over the available period.
   Hypothesis: Sales declined over time.

3. Compare the product's selling price and margin with other iPhone products.
   Hypothesis: Price positioning or margin may be associated with weaker sales.

4. Analyze cancellation and return behavior for the product.
   Hypothesis: Higher cancellations or returns may be associated with weaker performance.

WHY THIS IS GOOD:
- Step 1 establishes the baseline.
- Each step tests a different explanation.
- Every step can be answered from the available schema.


Example 2
USER QUESTION:
"Which iPhone model sells the most?"

GOOD PLAN:
1. Rank iPhone products by total units sold, excluding cancelled orders.

WHY:
One query can perform the grouping, aggregation and ranking.


Example 3
USER QUESTION:
"How have iPhone sales changed over time?"

GOOD PLAN:
1. Calculate monthly iPhone units sold across the available order_date range.

WHY:
This is a trend question and needs one time-series analysis.


Example 4
USER QUESTION:
"Why are MagSafe Charger sales weak?"

GOOD PLAN:
1. Compare MagSafe Charger units sold with other Accessories.
   Hypothesis: The product has below-average sales within its category.

2. Compare its return rate and return reasons with other Accessories.
   Hypothesis: Product issues may be associated with weaker performance.

3. Compare its selling price and margin with other Accessories.
   Hypothesis: Price positioning may affect demand.

4. Analyze its monthly sales trend.
   Hypothesis: Sales may have declined over time.

==================================================
OUTPUT REQUIREMENTS
==================================================

Return ONLY valid JSON.

Use exactly this structure:

{
  "question_type": "diagnostic|descriptive|comparative|trend",
  "steps": [
    {
      "id": 1,
      "goal": "...",
      "hypothesis": "..."
    }
  ]
}

Do not include Markdown.
Do not include explanations outside the JSON.
Do not add unnecessary steps."""

@dataclass
class StepResult:
    step: dict
    sql: str | None = None
    result: QueryResult | None = None
    attempts: int = 0
    repaired: bool = False
    error: str | None = None


@dataclass
class AnalysisReport:
    question: str
    plan: dict
    hints: str
    steps: list[StepResult] = field(default_factory=list)
    answer: str = ""


# --------------------------------------------------------------------------- #
# Entity detection (which product / category is the user talking about?)
# --------------------------------------------------------------------------- #
def _column(conn, sql: str) -> list[str]:
    cur = conn.cursor()
    try:
        cur.execute(sql)
        return [r[0].decode() if isinstance(r[0], (bytes, bytearray)) else r[0] for r in cur.fetchall()]
    finally:
        cur.close()


def find_products(question: str, conn, limit: int = 6) -> list[str]:
    names = _column(conn, "SELECT product_name FROM products")
    q = question.lower()

    # 1) full product name written in the question (word boundaries: "Model 1" != "Model 10")
    exact = [n for n in names if re.search(rf"(?<!\w){re.escape(n.lower())}(?!\w)", q)]
    if exact:
        return sorted(exact, key=len, reverse=True)[:limit]

    # 2) partial names: "iPhone 16 Pro" should find every "iPhone 16 Pro ..." variant
    words = re.findall(r"[\w'-]+", q)
    grams = {" ".join(words[i : i + n]) for n in (1, 2, 3, 4, 5) for i in range(len(words) - n + 1)}
    scored = []
    for name in names:
        lname = name.lower()
        best = max((SequenceMatcher(None, g, lname).ratio() for g in grams), default=0.0)
        covered = max(
            (len(g) for g in grams if len(g) >= 4 and re.search(rf"(?<!\w){re.escape(g)}(?!\w)", lname)),
            default=0,
        )
        if covered:
            best = max(best, 0.5 + 0.5 * covered / len(lname))
        if best >= 0.6:
            scored.append((best, name))
    return [n for _, n in sorted(scored, reverse=True)[:limit]]


def find_categories(question: str, conn) -> list[str]:
    q = question.lower()
    found = []
    for name in _column(conn, "SELECT category_name FROM categories"):
        stem = name.lower().rstrip("s")  # 'Laptops' -> 'laptop' (matches singular and plural)
        if re.search(rf"(?<!\w){re.escape(stem)}s?(?!\w)", q):
            found.append(name)
    return found


def hints_to_text(products: list[str], categories: list[str]) -> str:
    lines = []
    if products:
        lines.append("Products the user probably means (exact product_name values): " + ", ".join(products))
    if categories:
        lines.append("Categories mentioned (exact category_name values): " + ", ".join(categories))
    return "\n".join(lines) or "No specific product or category detected in the question."


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #
class SQLAnalyst:
    def __init__(self, client: OllamaClient | None = None, max_repairs: int | None = None, max_rows: int | None = None):
        self.client = client or OllamaClient()
        self.max_repairs = max_repairs if max_repairs is not None else int(os.getenv("MAX_REPAIR_ATTEMPTS", "3"))
        self.max_rows = max_rows or int(os.getenv("MAX_ROWS", "200"))

    # ---- step 1: plan ----
    def plan(self, question: str, schema_text: str, hints: str) -> dict:
        user = f"DATABASE SCHEMA:\n{schema_text}\n\nENTITY HINTS:\n{hints}\n\nUSER QUESTION:\n{question}"
        try:
            raw = self.client.chat_json(PLANNER_PROMPT, user, temperature=0.2)
        except OllamaError:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        steps = []
        for s in raw.get("steps") or []:
            if isinstance(s, dict) and s.get("goal"):
                steps.append({"id": len(steps) + 1, "goal": str(s["goal"]), "hypothesis": str(s.get("hypothesis", ""))})
            elif isinstance(s, str):
                steps.append({"id": len(steps) + 1, "goal": s, "hypothesis": ""})
        if not steps:  # planner failed -> answer the question directly with one query
            steps = [{"id": 1, "goal": question, "hypothesis": ""}]
        return {"question_type": raw.get("question_type", "unknown"), "steps": steps[:MAX_STEPS]}

    # ---- steps 2-5: generate -> validate -> execute -> repair ----
    def _run_step(self, conn, question: str, step: dict, schema_text: str, hints: str) -> StepResult:
        sql, last_error, empty_result = "", "", None
        for attempt in range(self.max_repairs + 1):
            try:
                if attempt == 0:
                    sql = generate_sql(self.client, question, step, schema_text, hints)
                else:
                    sql = repair_sql(self.client, question, step, schema_text, sql, last_error, hints)
            except OllamaError as e:
                return StepResult(step, sql or None, None, attempt, attempt > 0, str(e))

            check = validate_sql(sql, conn)
            sql = check.sql or sql
            if not check.ok:
                last_error = check.error or "Validation failed."
                continue

            result = execute_query(sql, conn, self.max_rows)
            if result.error:
                last_error = result.error
                continue
            if result.row_count == 0:
                empty_result = result
                last_error = (
                    "The query ran but returned 0 rows. Re-check the filters: exact product_name / category_name, "
                    "order_status values, date ranges and JOIN conditions."
                )
                continue
            return StepResult(step, sql, result, attempt + 1, attempt > 0)

        if empty_result is not None:  # tried to fix an empty result but it is genuinely empty
            return StepResult(step, empty_result.sql, empty_result, self.max_repairs + 1, True)
        return StepResult(step, sql, None, self.max_repairs + 1, True, last_error)

    # ---- full pipeline ----
    def analyze(self, question: str, progress: Callable[[str], None] | None = None) -> AnalysisReport:
        say = progress or (lambda _msg: None)
        conn = get_connection()
        try:
            say("Reading database schema...")
            schema = inspect_schema(conn)
            schema_text = schema_to_text(schema)
            ownership = column_ownership_text(schema)
            if ownership:
                schema_text += (
                    "\n\nCOLUMN LOCATIONS - use this exact table for each column. This is not optional "
                    "background info: writing a column on any other table will make the query fail.\n"
                    "Example: product_name is only ever `products.product_name` or `p.product_name` "
                    "(NEVER order_items.product_name / oi.product_name). category_name is only ever "
                    "`categories.category_name` or `c.category_name` (NEVER products.category_name); "
                    "products only has category_id, so filtering by category_name requires "
                    "JOIN categories c ON c.category_id = p.category_id.\n" + ownership
                )
            hints = hints_to_text(find_products(question, conn), find_categories(question, conn))

            say("Planning the analysis...")
            plan = self.plan(question, schema_text, hints)
            report = AnalysisReport(question=question, plan=plan, hints=hints)

            for step in plan["steps"]:
                say(f"Step {step['id']}/{len(plan['steps'])}: {step['goal']}")
                report.steps.append(self._run_step(conn, question, step, schema_text, hints))

            say("Writing the final answer...")
            report.answer = generate_answer(self.client, question, plan, report.steps)
            return report
        finally:
            conn.close()