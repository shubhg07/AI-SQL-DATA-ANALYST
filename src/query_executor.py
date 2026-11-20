"""Runs a validated query and returns the rows (with a row cap and a timeout)."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from decimal import Decimal

import mysql.connector


@dataclass
class QueryResult:
    sql: str
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    error: str | None = None
    elapsed_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return self.error is None

    def to_dataframe(self):
        import pandas as pd

        return pd.DataFrame(self.rows, columns=self.columns)


def _plain(value):
    """MySQL returns DECIMAL as Decimal; use float so pandas/charts/formatting behave."""
    return float(value) if isinstance(value, Decimal) else value


def _set_timeout(cur, timeout_s: float) -> None:
    try:  # MySQL 5.7.8+
        cur.execute(f"SET SESSION max_execution_time = {int(timeout_s * 1000)}")
    except mysql.connector.Error:
        try:  # MariaDB
            cur.execute(f"SET SESSION max_statement_time = {int(timeout_s)}")
        except mysql.connector.Error:
            pass


def execute_query(sql: str, conn, max_rows: int | None = None, timeout_s: float | None = None) -> QueryResult:
    max_rows = max_rows or int(os.getenv("MAX_ROWS", "200"))
    timeout_s = timeout_s or float(os.getenv("QUERY_TIMEOUT_SECONDS", "15"))
    started = time.perf_counter()
    cur = conn.cursor(buffered=True)
    try:
        _set_timeout(cur, timeout_s)
        cur.execute(sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        fetched = cur.fetchmany(max_rows + 1)
        return QueryResult(
            sql=sql,
            columns=columns,
            rows=[tuple(_plain(v) for v in row) for row in fetched[:max_rows]],
            row_count=min(len(fetched), max_rows),
            truncated=len(fetched) > max_rows,
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )
    except mysql.connector.Error as e:
        msg = f"Query timed out after {timeout_s:.0f}s." if getattr(e, "errno", None) in (3024, 1969) else str(e)
        return QueryResult(sql=sql, error=msg, elapsed_ms=(time.perf_counter() - started) * 1000)
    finally:
        cur.close()