"""Reads the LIVE MySQL schema and turns it into compact text for the LLM.

Besides tables/columns/foreign keys it adds two things that make the model far
more accurate: the exact values of small categorical columns (order_status,
category_name, return_reason...) and the min/max of date columns.
"""
from __future__ import annotations

from .database import _text


def _rows(conn, sql: str) -> list[tuple]:
    cur = conn.cursor()
    try:
        cur.execute(sql)
        return [tuple(_text(v) for v in row) for row in cur.fetchall()]
    finally:
        cur.close()


def inspect_schema(conn, max_categorical: int = 20) -> dict:
    tables = [
        r[0]
        for r in _rows(
            conn,
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE' ORDER BY table_name",
        )
    ]
    fks = {
        (t, c): f"{rt}.{rc}"
        for t, c, rt, rc in _rows(
            conn,
            "SELECT table_name, column_name, referenced_table_name, referenced_column_name "
            "FROM information_schema.key_column_usage "
            "WHERE table_schema = DATABASE() AND referenced_table_name IS NOT NULL",
        )
    }
    columns_by_table: dict[str, list] = {t: [] for t in tables}
    for t, name, ctype, dtype, key in _rows(
        conn,
        "SELECT table_name, column_name, column_type, data_type, column_key "
        "FROM information_schema.columns WHERE table_schema = DATABASE() "
        "ORDER BY table_name, ordinal_position",
    ):
        if t in columns_by_table:
            columns_by_table[t].append((name, ctype, dtype.lower(), key))

    schema: dict = {}
    for table in tables:
        row_count = _rows(conn, f"SELECT COUNT(*) FROM `{table}`")[0][0]
        columns = []
        for name, ctype, dtype, key in columns_by_table[table]:
            info = {"name": name, "type": ctype, "pk": key == "PRI", "fk": fks.get((table, name))}
            if info["fk"] is None and dtype in ("varchar", "char", "enum"):
                vals = [
                    r[0]
                    for r in _rows(
                        conn,
                        f"SELECT DISTINCT `{name}` FROM `{table}` "
                        f"WHERE `{name}` IS NOT NULL LIMIT {max_categorical + 1}",
                    )
                ]
                if 0 < len(vals) <= max_categorical:
                    info["values"] = sorted(vals)
            elif dtype in ("date", "datetime", "timestamp"):
                lo, hi = _rows(conn, f"SELECT MIN(`{name}`), MAX(`{name}`) FROM `{table}`")[0]
                if lo is not None:
                    info["range"] = (str(lo)[:10], str(hi)[:10])
            columns.append(info)
        schema[table] = {"row_count": row_count, "columns": columns}
    return schema


def schema_to_text(schema: dict) -> str:
    lines: list[str] = []
    for table, meta in schema.items():
        lines.append(f"TABLE {table} ({meta['row_count']} rows)")
        for c in meta["columns"]:
            parts = [f"  - {c['name']} {c['type']}"]
            if c["pk"]:
                parts.append("PRIMARY KEY")
            if c["fk"]:
                parts.append(f"-> {c['fk']}")
            if "range" in c:
                parts.append(f"range: {c['range'][0]} to {c['range'][1]}")
            if "values" in c:
                parts.append(f"values: {c['values']}")
            lines.append(" ".join(parts))
        lines.append("")
    return "\n".join(lines).strip()


def column_ownership_text(schema: dict) -> str:
    """A short column-name -> table lookup, e.g. 'product_name -> products'.

    Small/weaker models tend to get this exact thing wrong: they use the right column
    name but put it on the wrong table (oi.product_name instead of p.product_name).
    A short, unambiguous lookup list is much harder to misread than picking the right
    table back out of a long, multi-table schema dump. Columns that exist on more than
    one table (like every table's own primary key) are left out on purpose, since
    "id -> several tables" would only add noise, not clarity.
    """
    owners: dict[str, set[str]] = {}
    for table, meta in schema.items():
        for c in meta["columns"]:
            owners.setdefault(c["name"], set()).add(table)

    lines = [f"{name} -> {next(iter(tables))}" for name, tables in sorted(owners.items()) if len(tables) == 1]
    return "\n".join(lines)