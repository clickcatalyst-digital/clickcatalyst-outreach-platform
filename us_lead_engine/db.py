# us_lead_engine/db.py
# Connection + init for the independent us_leads.db.

import sqlite3
import os
import sys

from .config import DB_PATH

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")  # wait, don't error, on transient contention
    return conn


def init_db():
    """Create tables from schema.sql. Idempotent."""
    with open(SCHEMA_PATH) as f:
        schema = f.read()
    conn = get_conn()
    conn.executescript(schema)
    conn.commit()
    conn.close()
    print(f"✅ Initialized {DB_PATH}")


if __name__ == "__main__":
    if "--init" in sys.argv:
        init_db()
    else:
        print("Usage: python -m us_lead_engine.db --init")
