# api/routes/status.py
# Read-only control-panel status: is the MacBook online (heartbeat age), when did
# the workers last run, and a few headline counts. Pure Turso reads — no execution.

from fastapi import APIRouter
from ..database import get_conn

router = APIRouter()

ONLINE_THRESHOLD_MIN = 3   # Mac is "online" if the last heartbeat is younger than this


@router.get("/")
def system_status():
    conn = get_conn()
    cur = conn.cursor()

    def scalar(sql, default=None):
        try:
            r = cur.execute(sql).fetchone()
            return r[0] if r and r[0] is not None else default
        except Exception:
            return default

    # Heartbeat (online/offline + age) in one round-trip.
    hb = None
    try:
        hb = cur.execute(f"""
            SELECT Last_Beat_At,
                   ROUND((julianday('now') - julianday(Last_Beat_At)) * 1440, 1) AS age_min,
                   CASE WHEN (julianday('now') - julianday(Last_Beat_At)) * 1440 < {ONLINE_THRESHOLD_MIN}
                        THEN 1 ELSE 0 END AS online
            FROM mac_heartbeat WHERE ID = 1
        """).fetchone()
    except Exception:
        hb = None

    online = bool(hb["online"]) if hb else False

    result = {
        "mac_status": "online" if online else "offline",
        "last_heartbeat": hb["Last_Beat_At"] if hb else None,
        "heartbeat_age_min": hb["age_min"] if hb else None,
        "last_tracking_sync": scalar(
            "SELECT Last_Sync_At FROM tracking_sync_heartbeat WHERE ID = 1"),
        "last_orchestrator_cycle": scalar(
            "SELECT Config_Value FROM us_scheduler_config WHERE Config_Key = 'last_cycle_at'"),
        "us_leads": scalar(
            "SELECT COUNT(*) FROM company_enrichment WHERE Lead_Source = 'US_Apollo'", 0),
        "contacts": scalar("SELECT COUNT(*) FROM company_contacts", 0),
        "test_emails": scalar("SELECT COUNT(*) FROM us_test_emails", 0),
    }
    conn.close()
    return result
