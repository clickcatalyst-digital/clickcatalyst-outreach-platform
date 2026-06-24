# api/database.py
# Single source of truth for DB path and connection

import sqlite3
import os

DB_PATH = os.getenv(
    "DB_PATH",
    "/Users/pujan/Developer/data_collector/indian_companies/company_master_data.db"
)

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # returns dict-like rows
    return conn


def country_filter(country, cin_col="CIN", batch_col=None):
    """
    SQL WHERE fragment to scope a query by country.
      us    -> CIN LIKE 'APOLLO_%'   (Apollo leads)
      india -> CIN NOT LIKE 'APOLLO_%' (MCA leads)
      None / other -> no country scoping (all)
    If batch_col is given, also excludes test sends (Batch_ID LIKE 'ustest%').
    Returns a string starting with ' AND ...' (or '' if no filtering).
    """
    frags = []
    c = (country or "").lower()
    if c == "us":
        frags.append(f"{cin_col} LIKE 'APOLLO_%'")
    elif c == "india":
        frags.append(f"{cin_col} NOT LIKE 'APOLLO_%'")
    if batch_col:
        frags.append(f"{batch_col} NOT LIKE 'ustest%'")
    return (" AND " + " AND ".join(frags)) if frags else ""