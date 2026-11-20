"""MySQL connection helpers. AI-generated queries always use a read-only session."""
from __future__ import annotations

import os
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def get_db_name() -> str:
    return os.getenv("MYSQL_DATABASE", "novacart")


def _config(read_only: bool) -> dict:
    user = os.getenv("MYSQL_USER", "root")
    password = os.getenv("MYSQL_PASSWORD", "")
    if read_only and os.getenv("MYSQL_RO_USER"):  # dedicated SELECT-only account
        user = os.getenv("MYSQL_RO_USER", "")
        password = os.getenv("MYSQL_RO_PASSWORD", "")
    return {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": user,
        "password": password,
        "database": get_db_name(),
        "connection_timeout": 10,
    }


def get_connection(read_only: bool = True):
    """Open a MySQL connection. read_only=True also forces a read-only session."""
    conn = mysql.connector.connect(**_config(read_only))
    if read_only:
        cur = conn.cursor()
        cur.execute("SET SESSION TRANSACTION READ ONLY")
        cur.close()
    return conn


def check_database() -> tuple[bool, str]:
    """Used by the UI: can we connect, and is there data?"""
    try:
        conn = get_connection()
    except mysql.connector.Error as e:
        return False, f"Cannot connect to MySQL: {e}"
    try:
        tables = list_tables(conn)
        if not tables:
            return False, f"Database '{get_db_name()}' has no tables. Run: python database/seed_data.py"
        return True, f"Connected to '{get_db_name()}' ({len(tables)} tables)"
    finally:
        conn.close()


def list_tables(conn) -> list[str]:
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE' ORDER BY table_name"
        )
        return [_text(r[0]) for r in cur.fetchall()]
    finally:
        cur.close()


def _text(value):
    return value.decode() if isinstance(value, (bytes, bytearray)) else value