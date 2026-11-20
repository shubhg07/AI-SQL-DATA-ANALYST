"""Safety + syntax gate. Every generated query must pass here before it runs."""
from __future__ import annotations

import re
from dataclasses import dataclass

import mysql.connector

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|replace\s+into|drop|alter|create|truncate|rename|grant|revoke|"
    r"call|lock|unlock|handler|load|load_file|outfile|dumpfile|into|sleep|benchmark|kill|"
    r"shutdown|prepare|execute|deallocate)\b",
    re.IGNORECASE,
)
# The AI may only look at the business data, never at MySQL internals.
SYSTEM_SCHEMAS = re.compile(r"\b(mysql|information_schema|performance_schema|sys)\s*\.", re.IGNORECASE)

# One pass over the text: strings, backtick identifiers and comments are found left-to-right.
_MASK = re.compile(
    r"'(?:[^'\\]|\\.|'')*'"
    r'|"(?:[^"\\]|\\.|"")*"'
    r"|`[^`]*`"
    r"|/\*.*?\*/"
    r"|--[^\n]*"
    r"|#[^\n]*",
    re.S,
)


@dataclass
class ValidationResult:
    ok: bool
    sql: str
    error: str | None = None


def clean_sql(raw: str) -> str:
    """Strip markdown fences, whitespace and trailing semicolons."""
    sql = (raw or "").strip()
    fence = re.search(r"```(?:sql)?\s*(.*?)```", sql, re.S | re.I)
    if fence:
        sql = fence.group(1).strip()
    while sql.endswith(";"):
        sql = sql[:-1].rstrip()
    return sql


def _mask(sql: str) -> str:
    """Blank out comments, strings and quoted identifiers so keyword checks don't misfire."""
    return _MASK.sub(lambda m: " " if m.group(0).startswith(("/*", "--", "#")) else "''", sql)


def _has_unmatched_quote(sql: str) -> bool:
    """True if a ' or " string literal is left open, e.g. '2025-12-31 with no closing quote.

    _MASK only matches a string when its quotes are balanced, so any quote character
    left over after removing every balanced string/comment/identifier means one
    string literal never closed.
    """
    leftover = _MASK.sub("", sql)
    return "'" in leftover or '"' in leftover


def validate_sql(raw_sql: str, conn=None) -> ValidationResult:
    """Static safety checks; if a connection is given, MySQL also checks tables/columns via EXPLAIN."""
    sql = clean_sql(raw_sql)
    if not sql:
        return ValidationResult(False, sql, "The query is empty.")

    # Check this before anything keyword-based: with an unbalanced quote, everything after
    # it is misread as part of a string, so the checks below could pass or fail for the wrong reason.
    if _has_unmatched_quote(sql):
        return ValidationResult(
            False, sql,
            "This query has an unmatched quote character (' or \"). One string literal is missing its "
            "closing quote - for example '2025-12-31 GROUP BY ... instead of '2025-12-31' GROUP BY ... . "
            "Find that string and add the missing closing quote; do not change anything else."
        )

    masked = _mask(sql)
    if ";" in masked:
        return ValidationResult(False, sql, "Only one SQL statement is allowed.")
    if not re.match(r"^\s*(select|with)\b", masked, re.IGNORECASE):
        return ValidationResult(False, sql, "Only SELECT queries (optionally starting with WITH) are allowed.")
    hit = FORBIDDEN.search(masked)
    if hit:
        return ValidationResult(False, sql, f"Forbidden keyword: {hit.group(1).upper()}.")
    if SYSTEM_SCHEMAS.search(masked):
        return ValidationResult(False, sql, "Access to system schemas is not allowed.")

    if conn is not None:
        cur = conn.cursor()
        try:
            cur.execute(f"EXPLAIN {sql}")
            cur.fetchall()
        except mysql.connector.Error as e:
            return ValidationResult(False, sql, f"MySQL rejected the query: {e}")
        finally:
            cur.close()
    return ValidationResult(True, sql)