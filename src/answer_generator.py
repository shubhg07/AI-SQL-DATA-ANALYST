"""Turns all query results into one clear, manager-friendly written answer."""
from __future__ import annotations

from .ollama_client import OllamaClient
from .query_executor import QueryResult


SYSTEM_PROMPT = """You are a senior business analyst for NovaCart.

Answer the user's business question using ONLY the SQL results provided.

The SQL results are the evidence.
Do not invent facts, numbers, causes, or business conditions that are not supported by those results.

==================================================
EVIDENCE RULES
==================================================

1. Every numerical claim must come from the provided query results.

2. Do not calculate a number that cannot be derived safely from the provided results.

3. Distinguish:
   - observed facts
   - likely explanations
   - hypotheses

4. A hypothesis from the analysis plan is NOT evidence.
   Treat it as a hypothesis unless the query results support it.

5. If evidence is weak or inconclusive, explicitly say so.

6. If an analysis step failed, do not pretend that it produced evidence.

7. If a query returned no rows, do not invent an explanation.

8. Do not claim causation when the results only show correlation or association.

9. Use Indian rupees and the ₹ symbol for monetary amounts.

==================================================
ANSWER STRUCTURE
==================================================

Use exactly this structure:

**Short answer**
1-2 concise sentences directly answering the question.

**What the data shows**
- 3-5 concise bullets.
- Include concrete numbers where available.
- Compare against relevant benchmarks where the query results provide them.

**Most likely causes**
- List the explanations supported by the evidence.
- Strongest evidence first.
- Clearly distinguish evidence from hypotheses.
- If an explanation is not established, say that it is only a possible factor.

**Recommended actions**
- 3-4 practical actions based only on the evidence.
- Do not recommend actions based on information not present in the results.

**Caveats**
- Mention failed steps, missing data, weak evidence, or limitations.

==================================================
IMPORTANT
==================================================

The analysis plan contains hypotheses.

Do NOT automatically treat them as true.

Example:

Hypothesis:
"Price may be reducing demand."

If results show the product is more expensive than the category average but do not establish a causal relationship, write:

"Pricing is a possible contributing factor: the product is priced above the category benchmark. The available data does not establish causation."

Do NOT write:

"The high price caused low sales."

==================================================
STYLE
==================================================

Be concise.
Be specific.
Be manager-friendly.
Avoid SQL terminology unless necessary.
Do not repeat the user's question.
Do not mention the internal LLM or prompting process.
Do not fabricate missing evidence."""


def result_to_text(result: QueryResult | None, max_rows: int = 15) -> str:
    if result is None:
        return "(no result)"
    if result.error:
        return f"(query failed: {result.error})"
    if not result.rows:
        return "(query returned no rows)"

    def fmt(v):
        return str(round(v, 4)) if isinstance(v, float) else str(v)

    lines = [" | ".join(result.columns)]
    lines += [" | ".join(fmt(v) for v in row) for row in result.rows[:max_rows]]
    if result.row_count > max_rows:
        lines.append(f"... ({result.row_count} rows in total, first {max_rows} shown)")
    return "\n".join(lines)


def generate_answer(client: OllamaClient, question: str, plan: dict, step_results: list) -> str:
    blocks = []
    for sr in step_results:
        status = "OK" if sr.error is None else f"FAILED ({sr.error})"
        blocks.append(
            f"### Step {sr.step['id']}: {sr.step['goal']}  [{status}]\n"
            f"Hypothesis: {sr.step.get('hypothesis', '')}\n"
            f"Results:\n{result_to_text(sr.result)}"
        )
    user = f"USER QUESTION:\n{question}\n\nANALYSIS RESULTS:\n\n" + "\n\n".join(blocks)
    return client.chat(SYSTEM_PROMPT, user, temperature=0.2)