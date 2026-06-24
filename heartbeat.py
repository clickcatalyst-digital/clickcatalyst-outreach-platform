#!/usr/bin/env python3
# heartbeat.py
# Writes a single liveness timestamp to Turso so any UI can tell whether the
# MacBook is online. Run every minute by launchd (com.clickcatalyst.heartbeat).
#
# Online/offline is decided by the READER, not here: the Mac just stamps "I'm
# alive at time T (UTC)". When the Mac sleeps, this stops running and the
# timestamp goes stale -> the dashboard shows Offline.
#
# Writes through db_factory, so it lands in Turso when TURSO_URL/TURSO_AUTH_TOKEN
# are set (else local SQLite for dev). Touches ONLY the mac_heartbeat table.

import os
import socket
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()
import db_factory

DB_PATH = os.getenv(
    "DB_PATH",
    "/Users/pujan/Developer/data_collector/indian_companies/company_master_data.db",
)


def beat():
    conn = db_factory.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mac_heartbeat (
            ID INTEGER PRIMARY KEY CHECK (ID = 1),
            Last_Beat_At TEXT,   -- UTC, 'YYYY-MM-DD HH:MM:SS' (julianday-friendly)
            Host TEXT
        )
    """)
    conn.execute("""
        INSERT INTO mac_heartbeat (ID, Last_Beat_At, Host)
        VALUES (1, ?, ?)
        ON CONFLICT(ID) DO UPDATE SET
            Last_Beat_At = excluded.Last_Beat_At,
            Host         = excluded.Host
    """, (datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), socket.gethostname()))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    beat()
    print("heartbeat written")
