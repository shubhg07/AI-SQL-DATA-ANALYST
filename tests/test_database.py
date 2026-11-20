"""Tests for the validator, schema inspector, executor and the seeded MySQL data.

Run from the project root:  python -m pytest -v

* Tests marked "static" need nothing.
* Tests using the `conn` fixture need MySQL running and `python database/seed_data.py`
  already executed; otherwise they are skipped automatically.
"""
import sys
from pathlib import Path

import mysql.connector
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.database import get_connection, list_tables  # noqa: E402
from src.query_executor import execute_query  # noqa: E402
from src.schema_inspector import inspect_schema, schema_to_text  # noqa: E402
from src.sql_validator import clean_sql, validate_sql  # noqa: E402

EXPECTED_TABLES = {
    "categories", "products", "customers", "addresses",
    "orders", "order_items", "payments", "returns",
}


@pytest.fixture(scope="module")
def conn():
    try:
        c = get_connection()
    except mysql.connector.Error as e:
        pytest.skip(f"MySQL not reachable: {e}")
    if not EXPECTED_TABLES <= set(list_tables(c)):
        c.close()
        pytest.skip("Run `python database/seed_data.py` first.")
    yield c
    c.close()


# ---------------- validator (static) ---------------- #
@pytest.mark.parametrize("good", [
    "SELECT product_name FROM products;",
    "WITH t AS (SELECT * FROM products) SELECT COUNT(*) FROM t",
    "SELECT * FROM returns WHERE return_reason LIKE '%delete%'",   # keyword inside a string
    "SELECT REPLACE(product_name, 'Model', 'M') FROM products",     # REPLACE() is a function
    "SELECT `order_date` FROM orders /* update later */",           # keyword inside a comment
])
def test_validator_accepts_safe_queries(good):
    assert validate_sql(good).ok


@pytest.mark.parametrize("bad", [
    "DROP TABLE products",
    "DELETE FROM products",
    "UPDATE products SET selling_price = 0",
    "INSERT INTO categories VALUES (1, 'x', 'y')",
    "SELECT 1; DROP TABLE products",
    "SELECT * FROM products INTO OUTFILE '/tmp/x.txt'",
    "SELECT SLEEP(30)",
    "SELECT * FROM information_schema.tables",
    "SELECT * FROM mysql.user",
    "SHOW TABLES",
    "",
])
def test_validator_blocks_dangerous_sql(bad):
    assert not validate_sql(bad).ok


def test_clean_sql_strips_fences_and_semicolon():
    assert clean_sql("```sql\nSELECT 1;\n```") == "SELECT 1"


@pytest.mark.parametrize("bad", [
    "SELECT * FROM orders WHERE order_date > '2025-12-31",              # missing closing quote
    "SELECT * FROM products WHERE brand = 'Apple' AND category = 'x",   # second string never closes
    'SELECT * FROM products WHERE brand = "Apple',                      # double-quote variant
])
def test_validator_catches_unmatched_quote(bad):
    result = validate_sql(bad)
    assert not result.ok and "unmatched quote" in result.error.lower()


def test_validator_gives_specific_message_for_real_broken_query():
    # This is the exact query an 8B model produced with a dropped closing quote on '2025-12-31.
    broken = (
        "SELECT SUM(oi.quantity) AS units FROM order_items oi JOIN orders o ON o.order_id = oi.order_id "
        "WHERE o.order_date BETWEEN '2025-01-01' AND '2025-12-31 GROUP BY o.order_id"
    )
    result = validate_sql(broken)
    assert not result.ok
    assert "unmatched quote" in result.error.lower()
    # it should NOT surface MySQL's confusing generic "near '%m')" style message instead
    assert "near" not in result.error.lower()


# ---------------- database ---------------- #
def test_all_tables_exist(conn):
    assert EXPECTED_TABLES <= set(list_tables(conn))


def test_tables_have_rows(conn):
    cur = conn.cursor()
    for table in EXPECTED_TABLES:
        cur.execute(f"SELECT COUNT(*) FROM `{table}`")
        assert cur.fetchone()[0] > 0, table


def test_no_orphan_order_items(conn):
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM order_items oi LEFT JOIN orders o ON o.order_id = oi.order_id "
        "WHERE o.order_id IS NULL"
    )
    assert cur.fetchone()[0] == 0


def test_session_is_read_only(conn):
    cur = conn.cursor()
    with pytest.raises(mysql.connector.Error):
        cur.execute("DELETE FROM categories WHERE category_id = -1")


def test_planted_underperformers_sell_below_median(conn):
    story_file = ROOT / "database" / "underperformers.txt"
    if not story_file.exists():
        pytest.skip("underperformers.txt not found (run the seed script).")
    cur = conn.cursor()
    cur.execute(
        """SELECT p.product_name, SUM(oi.quantity)
           FROM order_items oi JOIN products p ON p.product_id = oi.product_id
           GROUP BY p.product_name"""
    )
    units = dict(cur.fetchall())
    median = sorted(units.values())[len(units) // 2]
    for line in story_file.read_text(encoding="utf-8").splitlines():
        name = line.split("|")[0]
        assert units[name] < median, name


# ---------------- schema inspector ---------------- #
def test_schema_text_has_tables_values_and_ranges(conn):
    text = schema_to_text(inspect_schema(conn))
    assert "TABLE order_items" in text
    assert "order_item_id int" in text and "PRIMARY KEY" in text
    assert "-> orders.order_id" in text              # foreign key
    assert "Delivered" in text and "Cancelled" in text   # categorical values
    assert "iPhone" in text and "AirPods" in text        # category names
    assert "range: 2025-01" in text                  # date range


def test_column_ownership_catches_the_exact_bugs_seen_in_practice(conn):
    from src.schema_inspector import column_ownership_text
    text = column_ownership_text(inspect_schema(conn))
    # product_name lives on products, NOT order_items (a real 3B-model mistake: oi.product_name)
    assert "product_name -> products" in text
    # category_name lives on categories, NOT products (a real mistake: products.category_name)
    assert "category_name -> categories" in text
    # a genuinely multi-table column (product_id: a PK on products, a FK on order_items and reviews)
    # is ambiguous, so it must be left out rather than guessed at
    assert "product_id ->" not in text


# ---------------- validator with MySQL (EXPLAIN) ---------------- #
def test_validator_catches_unknown_column(conn):
    result = validate_sql("SELECT no_such_column FROM products", conn)
    assert not result.ok and "unknown column" in result.error.lower()


def test_validator_catches_unknown_table(conn):
    result = validate_sql("SELECT * FROM missing_table", conn)
    assert not result.ok and "doesn't exist" in result.error.lower()


def test_validator_accepts_real_analysis_query(conn):
    sql = (
        "SELECT p.product_name, SUM(oi.quantity) AS units FROM order_items oi "
        "JOIN products p ON p.product_id = oi.product_id GROUP BY p.product_name ORDER BY units LIMIT 5"
    )
    assert validate_sql(sql, conn).ok


# ---------------- executor ---------------- #
def test_executor_returns_rows_and_floats(conn):
    result = execute_query("SELECT product_name, selling_price FROM products ORDER BY selling_price", conn)
    assert result.ok and result.columns == ["product_name", "selling_price"]
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM products")
    assert result.row_count == cur.fetchone()[0]
    assert isinstance(result.rows[0][1], float)      # Decimal converted


def test_executor_row_cap(conn):
    result = execute_query("SELECT * FROM order_items", conn, max_rows=5)
    assert result.row_count == 5 and result.truncated


def test_executor_reports_errors(conn):
    result = execute_query("SELECT * FROM missing_table", conn)
    assert not result.ok and "doesn't exist" in result.error.lower()