#!/usr/bin/env python3
# command_worker.py
# Drains dashboard-triggered actions from Turso and runs them on the Mac. The hosted
# dashboard can only WRITE Turso, so "trigger" buttons enqueue an intent row here and
# the Mac executes it on the next tick.
#
#   command_queue (Action='run_once')  -> orchestrator.run_cycle(force=True)
#   discover_jobs (Status='pending')   -> discovery (Google Places) via _execute_job
#
# discover reuses the existing discover_jobs table (it is already a job queue), so the
# dashboard enqueues a discover by inserting a pending discover_jobs row, exactly like
# POST /api/discover/run does. Run once per tick (added to scripts/tick.sh).
# Touches only Turso shared state; us_leads.db corpus stays Mac-local.

import json
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()
import db_factory
from us_lead_engine.config import MAIN_DB_PATH


def _now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS command_queue (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            Action TEXT NOT NULL,            -- 'run_once' (discover uses discover_jobs)
            Payload TEXT,                    -- JSON args, optional
            Status TEXT DEFAULT 'pending',   -- pending | running | done | failed
            Requested_At TEXT,
            Started_At TEXT,
            Finished_At TEXT,
            Result TEXT
        )
    """)
    conn.commit()


def _run_command(conn, cmd):
    cid, action = cmd["ID"], cmd["Action"]
    conn.execute("UPDATE command_queue SET Status='running', Started_At=? WHERE ID=?", (_now(), cid))
    conn.commit()
    try:
        if action == "run_once":
            from us_lead_engine import orchestrator
            orchestrator.run_cycle(verbose=False, force=True)
            result = "ok"
        else:
            raise ValueError(f"unknown action: {action}")
        conn.execute("UPDATE command_queue SET Status='done', Finished_At=?, Result=? WHERE ID=?",
                     (_now(), result, cid))
    except Exception as e:
        conn.execute("UPDATE command_queue SET Status='failed', Finished_At=?, Result=? WHERE ID=?",
                     (_now(), str(e)[:500], cid))
    conn.commit()
    print(f"[command_worker] command {cid} ({action}) -> done")


def drain_commands(conn):
    ensure_table(conn)
    pending = [dict(r) for r in conn.execute(
        "SELECT ID, Action, Payload FROM command_queue WHERE Status='pending' ORDER BY ID"
    ).fetchall()]
    for cmd in pending:
        _run_command(conn, cmd)
    return len(pending)


def drain_discover_jobs():
    """Run any pending discover_jobs (enqueued by the dashboard) via the existing executor."""
    conn = db_factory.connect(MAIN_DB_PATH)
    rows = [dict(r) for r in conn.execute(
        "SELECT Job_ID, Query_Text, City_Hint FROM discover_jobs WHERE Status='pending' ORDER BY Job_ID"
    ).fetchall()]
    conn.close()
    if not rows:
        return 0
    from api.routes.discover import _execute_job  # heavy import; only when there is work
    for r in rows:
        try:
            _execute_job(r["Job_ID"], r["Query_Text"], r.get("City_Hint"))
            print(f"[command_worker] discover job {r['Job_ID']} executed")
        except Exception as e:
            print(f"[command_worker] discover job {r['Job_ID']} failed: {e}")
    return len(rows)


def main():
    conn = db_factory.connect(MAIN_DB_PATH)
    n_cmd = drain_commands(conn)
    conn.close()
    n_disc = drain_discover_jobs()
    print(f"[command_worker] processed {n_cmd} command(s), {n_disc} discover job(s)")


if __name__ == "__main__":
    main()
