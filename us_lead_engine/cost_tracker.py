# us_lead_engine/cost_tracker.py
# Logs every API call's credit + $ cost, and prints a spend report (concern #2).

from .db import get_conn
from .config import CURRENT_PLAN, usd_per_credit


def log_call(endpoint, call_type, credits_used=0, results_returned=0,
             emails_revealed=0, notes=""):
    """Record one API call in api_usage_log."""
    usd = round(credits_used * usd_per_credit(), 4)
    conn = get_conn()
    conn.execute("""
        INSERT INTO api_usage_log
            (Endpoint, Call_Type, Credits_Used, Results_Returned,
             Emails_Revealed, Plan, USD_Cost, Notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (endpoint, call_type, credits_used, results_returned,
          emails_revealed, CURRENT_PLAN, usd, notes))
    conn.commit()
    conn.close()
    return usd


def spend_report():
    """Print total spend, broken down by call type."""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            COUNT(*) AS calls,
            COALESCE(SUM(Credits_Used), 0) AS credits,
            COALESCE(SUM(Emails_Revealed), 0) AS emails,
            COALESCE(SUM(USD_Cost), 0) AS usd
        FROM api_usage_log
    """)
    total = dict(cur.fetchone())

    cur.execute("""
        SELECT Call_Type,
               COUNT(*) AS calls,
               COALESCE(SUM(Credits_Used), 0) AS credits,
               COALESCE(SUM(Results_Returned), 0) AS results,
               COALESCE(SUM(Emails_Revealed), 0) AS emails,
               COALESCE(SUM(USD_Cost), 0) AS usd
        FROM api_usage_log
        GROUP BY Call_Type
    """)
    by_type = [dict(r) for r in cur.fetchall()]
    conn.close()

    print("💰 SPEND REPORT")
    print(f"   Plan: {CURRENT_PLAN}  (${usd_per_credit():.4f} / reveal credit)")
    print(f"   {'Type':<10} {'Calls':>6} {'Credits':>8} {'Results':>8} {'Emails':>7} {'USD':>8}")
    print(f"   {'-'*10} {'-'*6} {'-'*8} {'-'*8} {'-'*7} {'-'*8}")
    for r in by_type:
        print(f"   {r['Call_Type']:<10} {r['calls']:>6} {r['credits']:>8} "
              f"{r['results']:>8} {r['emails']:>7} ${r['usd']:>7.2f}")
    print(f"   {'-'*10} {'-'*6} {'-'*8} {'-'*8} {'-'*7} {'-'*8}")
    print(f"   {'TOTAL':<10} {total['calls']:>6} {total['credits']:>8} "
          f"{'':>8} {total['emails']:>7} ${total['usd']:>7.2f}")

    if total["emails"] > 0:
        print(f"\n   Cost per revealed email: ${total['usd'] / total['emails']:.4f}")
    return total
