#!/usr/bin/env python3
"""
us_lead_engine/orchestrator.py

Self-running brain for US outreach. Each cycle it:
  1. checks it's enabled, past the start date, and inside the CST send window
  2. computes today's volume = warmup ramp x Bayesian deliverability multiplier
  3. spreads remaining sends across the window (doesn't burst)
  4. drains the corpus of unsent leads; in PROD, auto-replenishes from Apollo
     (search -> enrich -> export) within a monthly credit cap when corpus is low
  5. sends via sender.send_one (TEST -> test emails, no prod state change;
     PROD -> real leads, advances pipeline)
  6. recomputes alerts (bounce rate, reputation, failures, corpus/credits low)

TEST vs PROD: test sends use Batch_ID 'ustest' and are excluded from all prod
warmup/volume math, so flipping back to PROD resumes exactly where it left off.

CLI:
  python -m us_lead_engine.orchestrator --init     # tables + defaults (start = next Mon)
  python -m us_lead_engine.orchestrator --once      # one cycle
  python -m us_lead_engine.orchestrator --daemon    # loop every cycle_minutes
  python -m us_lead_engine.orchestrator --status     # print status JSON
"""

import os
import sys
import json
import time
import math
import argparse
import sqlite3
from datetime import datetime, date, timedelta
try:
    from zoneinfo import ZoneInfo
    CST = ZoneInfo("America/Chicago")
except Exception:
    CST = None

from .config import MAIN_DB_PATH
from . import sender
import db_factory

DEFAULTS = {
    "mode": "test",                 # test | prod
    "enabled": "true",              # master on/off
    "test_count": "5",              # emails per cycle-day in test mode
    "start_hour": "9",              # CST window
    "end_hour": "17",
    "send_days": "0,1,2,3,4",       # Mon-Fri
    "replenish_threshold": "10",    # if corpus < this (prod) -> replenish
    "replenish_enrich_batch": "10", # leads to enrich per replenish
    "monthly_enrich_cap": "90",     # safety cap on Apollo reveals/month
    "cycle_minutes": "20",
    "learning_threshold": "150",    # prod sends before send-time learning kicks in
}


# ---------------------------------------------------------------------------
# CONFIG / SCHEMA
# ---------------------------------------------------------------------------

def _conn():
    # Main shared DB: Turso when TURSO_URL/TURSO_AUTH_TOKEN are set, else local SQLite.
    # (us_leads.db corpus connections below stay on raw sqlite3 — Mac-only.)
    return db_factory.connect(MAIN_DB_PATH)


def ensure_tables():
    """Quiet, idempotent schema + defaults (safe to call on API startup)."""
    conn = _conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS us_scheduler_config (
            Config_Key TEXT PRIMARY KEY,
            Config_Value TEXT,
            Updated_At DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS us_test_emails (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            Email TEXT UNIQUE NOT NULL,
            Added_At DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS us_alerts (
            ID INTEGER PRIMARY KEY AUTOINCREMENT,
            Level TEXT,            -- red | yellow | green
            Code TEXT UNIQUE,      -- one row per alert type (upserted)
            Message TEXT,
            Active INTEGER DEFAULT 1,
            Updated_At DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # Seed defaults (don't overwrite existing).
    for k, v in DEFAULTS.items():
        conn.execute("INSERT OR IGNORE INTO us_scheduler_config (Config_Key, Config_Value) VALUES (?, ?)", (k, v))
    # start_date = upcoming Monday (today if already Monday and before window end).
    if not conn.execute("SELECT 1 FROM us_scheduler_config WHERE Config_Key='start_date'").fetchone():
        today = date.today()
        days_ahead = (7 - today.weekday()) % 7  # 0=Mon
        nxt_mon = today + timedelta(days=days_ahead or (0 if today.weekday() == 0 else 7))
        if today.weekday() == 0:
            nxt_mon = today
        conn.execute("INSERT INTO us_scheduler_config (Config_Key, Config_Value) VALUES ('start_date', ?)",
                     (nxt_mon.isoformat(),))
    conn.commit()
    conn.close()


def init_db():
    ensure_tables()
    cfg = get_config()
    print(f"✅ Orchestrator initialized. Start date: {cfg.get('start_date')}, mode: {cfg.get('mode')}")


def get_config():
    conn = _conn()
    try:
        rows = conn.execute("SELECT Config_Key, Config_Value FROM us_scheduler_config").fetchall()
        return {r[0]: r[1] for r in rows}
    except sqlite3.OperationalError:
        return {}
    finally:
        conn.close()


def set_config(key, value):
    conn = _conn()
    conn.execute("""
        INSERT INTO us_scheduler_config (Config_Key, Config_Value, Updated_At)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(Config_Key) DO UPDATE SET Config_Value=excluded.Config_Value, Updated_At=CURRENT_TIMESTAMP
    """, (key, str(value)))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# WINDOW / TIMING
# ---------------------------------------------------------------------------

def _now_cst():
    return datetime.now(CST) if CST else datetime.now()


def in_window(cfg):
    now = _now_cst()
    days = [int(x) for x in cfg.get("send_days", "0,1,2,3,4").split(",") if x.strip()]
    sh, eh = int(cfg.get("start_hour", 9)), int(cfg.get("end_hour", 17))
    if now.weekday() not in days:
        return False, f"not a send day ({now.strftime('%a')})"
    if now.hour < sh or now.hour >= eh:
        return False, f"outside window ({now.hour}:00 CST, {sh}-{eh})"
    return True, "in window"


def before_start(cfg):
    sd = cfg.get("start_date")
    if not sd:
        return False
    return date.today() < date.fromisoformat(sd)


def _deliverability_multiplier():
    try:
        from bayesian_engine import get_volume_adjustment, should_send_today
        ok, _, score = should_send_today()
        return (get_volume_adjustment() if ok else 0.0), round(score, 3)
    except Exception:
        return 1.0, None


def learned_peak_hours(conn, cfg):
    """
    Send-time learning. Once >= learning_threshold PROD sends exist, compute which
    hours have the best open rate and return them as 'peak hours' to concentrate into.
    Until the threshold (or if tracking shows no opens), returns inactive → even spread.
    """
    thr = int(cfg.get("learning_threshold", 150))
    rows = conn.execute(f"""
        SELECT Send_Hour AS h, COUNT(*) AS sent,
               SUM(CASE WHEN Email_Opened = 1 THEN 1 ELSE 0 END) AS opened
        FROM outreach_analytics oa JOIN company_enrichment e ON oa.CIN = e.CIN
        WHERE e.Lead_Source = 'US_Apollo' AND oa.Batch_ID NOT LIKE '{sender.TEST_BATCH}%'
              AND Send_Hour IS NOT NULL
        GROUP BY Send_Hour
    """).fetchall()
    total = sum(r["sent"] for r in rows)
    if total < thr:
        return {"active": False, "sends": total, "threshold": thr, "peak_hours": []}

    # Open rate per hour, only hours with a stable sample.
    rates = [(r["h"], r["opened"] / r["sent"]) for r in rows if r["sent"] >= 5]
    rated = [r for _, r in rates if r > 0]
    if not rated:
        # Threshold met but no opens yet (e.g., tracking not live) → don't bias.
        return {"active": True, "sends": total, "threshold": thr, "peak_hours": []}
    avg = sum(rated) / len(rated)
    peaks = sorted([h for h, rt in rates if rt >= avg and rt > 0])
    return {"active": True, "sends": total, "threshold": thr, "peak_hours": peaks}


def _test_sent_today(conn):
    return conn.execute(
        f"SELECT COUNT(*) FROM outreach_analytics WHERE Batch_ID LIKE '{sender.TEST_BATCH}%' "
        f"AND Email_Sent_Date = date('now')"
    ).fetchone()[0]


def _reveals_this_month(conn):
    """Apollo reveal credits used this month (local estimate from us_leads.db cost log)."""
    try:
        from .config import DB_PATH as US_DB
        uc = sqlite3.connect(US_DB)
        n = uc.execute("""
            SELECT COALESCE(SUM(Credits_Used),0) FROM api_usage_log
            WHERE Call_Type='reveal' AND Created_At >= date('now','start of month')
        """).fetchone()[0]
        uc.close()
        return n or 0
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# ALERTS
# ---------------------------------------------------------------------------

def _set_alert(conn, code, level, message):
    conn.execute("""
        INSERT INTO us_alerts (Code, Level, Message, Active, Updated_At)
        VALUES (?, ?, ?, 1, CURRENT_TIMESTAMP)
        ON CONFLICT(Code) DO UPDATE SET Level=excluded.Level, Message=excluded.Message,
            Active=1, Updated_At=CURRENT_TIMESTAMP
    """, (code, level, message))


def _clear_alert(conn, code):
    conn.execute("UPDATE us_alerts SET Active=0, Updated_At=CURRENT_TIMESTAMP WHERE Code=?", (code,))


def recompute_alerts(conn, cfg):
    # Deliverability
    mult, score = _deliverability_multiplier()
    if score is not None and score < 0.4:
        _set_alert(conn, "deliverability", "red", f"Reputation low ({score}); sending paused/reduced.")
    elif score is not None and score < 0.6:
        _set_alert(conn, "deliverability", "yellow", f"Reputation moderate ({score}); volume reduced.")
    else:
        _clear_alert(conn, "deliverability")

    # Bounce rate (last 7 days, prod only)
    row = conn.execute(f"""
        SELECT COUNT(*) total, SUM(CASE WHEN Bounced=1 THEN 1 ELSE 0 END) bounced
        FROM outreach_analytics oa JOIN company_enrichment e ON oa.CIN=e.CIN
        WHERE e.Lead_Source='US_Apollo' AND oa.Batch_ID NOT LIKE '{sender.TEST_BATCH}%'
          AND oa.Email_Sent_Date >= date('now','-7 days')
    """).fetchone()
    total, bounced = row[0] or 0, row[1] or 0
    if total >= 10 and (bounced / total) > 0.05:
        _set_alert(conn, "bounce_rate", "red", f"Bounce rate {round(100*bounced/total,1)}% over last 7d ({bounced}/{total}).")
    else:
        _clear_alert(conn, "bounce_rate")

    # Corpus
    remaining = sender.corpus_remaining(conn)
    if remaining == 0:
        _set_alert(conn, "corpus_empty", "yellow", "Corpus empty — replenishing from Apollo (prod) or add leads.")
    elif remaining < int(cfg.get("replenish_threshold", 10)):
        _set_alert(conn, "corpus_low", "yellow", f"Corpus low ({remaining} leads left).")
    else:
        _clear_alert(conn, "corpus_low")
        _clear_alert(conn, "corpus_empty")

    # Credit cap
    used = _reveals_this_month(conn)
    cap = int(cfg.get("monthly_enrich_cap", 90))
    if used >= cap:
        _set_alert(conn, "credit_cap", "yellow", f"Monthly Apollo reveal cap hit ({used}/{cap}); replenish paused.")
    else:
        _clear_alert(conn, "credit_cap")

    # SMTP send health — infra failures (auth/connection) are NOT recipient bounces.
    serr = conn.execute(f"""
        SELECT Send_Error FROM outreach_analytics oa JOIN company_enrichment e ON oa.CIN = e.CIN
        WHERE e.Lead_Source = 'US_Apollo' AND oa.Batch_ID NOT LIKE '{sender.TEST_BATCH}%'
              AND oa.Send_Error IS NOT NULL AND oa.Email_Sent_Date >= date('now', '-1 days')
        ORDER BY oa.Analytics_ID DESC LIMIT 1
    """).fetchone()
    smtp_sigs = ("authentication", "username and password", "login", "credentials",
                 "connection", "timed out", "5.7.", "not accepted", "smtp")
    if serr and serr[0] and any(s in serr[0].lower() for s in smtp_sigs):
        _set_alert(conn, "smtp", "red",
                   f"Email sending is failing (SMTP/auth) — check SENDER_APP_PASS / Gmail. Last: {serr[0][:110]}")
    else:
        _clear_alert(conn, "smtp")

    # Tracking-sync health — opens/clicks only reach SQLite if sync_outreach_tracking.py runs.
    try:
        hb = conn.execute("SELECT Last_Sync_At FROM tracking_sync_heartbeat WHERE ID = 1").fetchone()
    except sqlite3.OperationalError:
        hb = None
    prod_sent = conn.execute(f"""
        SELECT COUNT(*) FROM outreach_analytics oa JOIN company_enrichment e ON oa.CIN = e.CIN
        WHERE e.Lead_Source = 'US_Apollo' AND oa.Batch_ID NOT LIKE '{sender.TEST_BATCH}%'
    """).fetchone()[0]
    if hb and hb[0]:
        try:
            age_min = (datetime.utcnow() - datetime.fromisoformat(hb[0])).total_seconds() / 60
        except Exception:
            age_min = 9999
        if age_min > 30:
            _set_alert(conn, "tracking_sync", "yellow",
                       f"Open/click sync stale ({int(age_min)}m) — opens may not be updating; reputation runs partly blind.")
        else:
            _clear_alert(conn, "tracking_sync")
    elif prod_sent > 0:
        _set_alert(conn, "tracking_sync", "yellow",
                   "Open/click sync has never run — opens won't reach the dashboard. Start sync_outreach_tracking.py.")
    else:
        _clear_alert(conn, "tracking_sync")

    # Positive: replies (last 7 days)
    replies = conn.execute(f"""
        SELECT COUNT(*) FROM outreach_analytics oa JOIN company_enrichment e ON oa.CIN=e.CIN
        WHERE e.Lead_Source='US_Apollo' AND oa.Reply_Received=1
          AND oa.Email_Sent_Date >= date('now','-14 days')
    """).fetchone()[0]
    if replies > 0:
        _set_alert(conn, "replies", "green", f"🎉 {replies} repl{'y' if replies==1 else 'ies'} in the last 14 days — follow up!")
    else:
        _clear_alert(conn, "replies")

    conn.commit()


# ---------------------------------------------------------------------------
# REPLENISH (prod only, credit-capped)
# ---------------------------------------------------------------------------

def replenish(conn, cfg):
    used = _reveals_this_month(conn)
    cap = int(cfg.get("monthly_enrich_cap", 90))
    if used >= cap:
        print(f"   [replenish] credit cap reached ({used}/{cap}) — skipping")
        return
    batch = min(int(cfg.get("replenish_enrich_batch", 10)), cap - used)
    page = int(cfg.get("search_page", "1"))
    print(f"   [replenish] corpus low — search page {page} + enrich {batch} + export")
    try:
        from . import run_discovery
        n = run_discovery.run_search(page=page)     # free; advances pages so new leads appear
        # Advance to the next page next time; restart at 1 when the query is exhausted.
        set_config("search_page", "1" if not n else str(page + 1))
        run_discovery.run_enrich(batch)             # costs <= batch credits
        run_discovery.run_export()                  # free
        _clear_alert(conn, "apollo"); conn.commit()
    except Exception as e:
        print(f"   [replenish] failed: {e}")
        _set_alert(conn, "apollo", "yellow", f"Apollo replenish failed (key/quota/network?): {str(e)[:130]}")
        conn.commit()


# ---------------------------------------------------------------------------
# CYCLE
# ---------------------------------------------------------------------------

def cycle_volume(conn, cfg):
    """How many to send THIS cycle, spreading remaining across the window."""
    limit, day = sender.warmup_limit(conn)
    mult, score = _deliverability_multiplier()
    day_target = int(limit * mult)
    sent = sender.sent_today(conn)
    remaining = max(0, day_target - sent)
    if remaining == 0:
        return 0, day, limit, sent, score

    now = _now_cst()
    eh = int(cfg.get("end_hour", 17))
    cyc_min = max(5, int(cfg.get("cycle_minutes", 20)))
    cycles_left = max(1, math.ceil(((eh - now.hour) * 60) / cyc_min))
    per_cycle = max(1, math.ceil(remaining / cycles_left))

    # Send-time learning: once active, concentrate volume into the best hours.
    learn = learned_peak_hours(conn, cfg)
    peaks = learn["peak_hours"]
    if learn["active"] and peaks:
        if now.hour in peaks:
            cycles_per_hour = max(1, 60 // cyc_min)
            peaks_left = [h for h in peaks if now.hour <= h < eh] or [now.hour]
            per_cycle = max(1, math.ceil(remaining / (len(peaks_left) * cycles_per_hour)))
        elif any(now.hour < h < eh for h in peaks):
            per_cycle = 0   # hold — a better-performing hour is still coming today

    return min(per_cycle, remaining), day, limit, sent, score


def run_cycle(verbose=True, force=False):
    """force=True bypasses the start-date + send-window gates (manual UI test trigger)."""
    conn = _conn()
    sender._ensure_columns(conn)
    cfg = get_config()
    if not cfg:
        print("   Not initialized — run: python -m us_lead_engine.orchestrator --init")
        conn.close(); return

    recompute_alerts(conn, cfg)
    set_config("last_cycle_at", _now_cst().isoformat())   # heartbeat — proves the daemon is alive

    if cfg.get("enabled", "true") != "true":
        if verbose: print("   ⏸ disabled")
        conn.close(); return
    if not force:
        if before_start(cfg):
            if verbose: print(f"   ⏳ waiting for start date {cfg.get('start_date')}")
            conn.close(); return
        ok, why = in_window(cfg)
        if not ok:
            if verbose: print(f"   ⏸ {why}")
            conn.close(); return

    mode = cfg.get("mode", "test")

    if mode == "test":
        n_total = int(cfg.get("test_count", 5))
        done = _test_sent_today(conn)
        n = max(0, n_total - done)
        test_emails = sender.get_test_emails(conn)
        if not test_emails:
            _set_alert(conn, "no_test_emails", "yellow", "Test mode on but no test emails configured.")
            conn.commit(); conn.close()
            if verbose: print("   ⚠ test mode on but no test emails set")
            return
        _clear_alert(conn, "no_test_emails"); conn.commit()
        if n == 0:
            if verbose: print(f"   ✅ test daily count reached ({done}/{n_total})")
            conn.close(); return
        leads = sender.fetch_sendable(conn, n)
        if not leads:
            if verbose: print("   ○ no corpus leads to render for test")
            conn.close(); return
        if verbose: print(f"   🧪 TEST: sending {len(leads)} to {test_emails}")
        for i, lead in enumerate(leads):
            to = test_emails[i % len(test_emails)]
            ok, err = sender.send_one(conn, lead, test_email=to, batch_prefix=sender.TEST_BATCH)
            if verbose: print(f"      {'✅' if ok else '❌'} {to} ({lead['Company_Name']})" + ("" if ok else f" — {err}"))
        conn.close()
        return

    # PROD
    if sender.corpus_remaining(conn) < int(cfg.get("replenish_threshold", 10)):
        replenish(conn, cfg)

    per_cycle, day, limit, sent, score = cycle_volume(conn, cfg)
    if per_cycle == 0:
        if verbose: print(f"   ✅ day target met (day {day}, limit {limit}, sent {sent})")
        conn.close(); return

    leads = sender.fetch_sendable(conn, per_cycle)
    if not leads:
        if verbose: print("   ○ corpus empty (replenish exhausted)")
        conn.close(); return

    if verbose: print(f"   🚀 PROD: sending {len(leads)} (day {day}, limit {limit}, "
                      f"sent {sent}, rep {score})")
    import random, time as _t
    for lead in leads:
        ok, err = sender.send_one(conn, lead, batch_prefix=sender.PROD_BATCH)
        if verbose: print(f"      {'✅' if ok else '❌'} {lead['Email_Address']} ({lead['Company_Name']})"
                          + ("" if ok else f" — {err}"))
        _t.sleep(random.uniform(15, 35))
    conn.close()


# ---------------------------------------------------------------------------
# STATUS
# ---------------------------------------------------------------------------

def status():
    conn = _conn()
    cfg = get_config()
    limit, day = sender.warmup_limit(conn)
    mult, score = _deliverability_multiplier()
    ok, why = in_window(cfg)
    alerts = [dict(r) for r in conn.execute(
        "SELECT Level, Code, Message FROM us_alerts WHERE Active=1 ORDER BY CASE Level WHEN 'red' THEN 0 WHEN 'yellow' THEN 1 ELSE 2 END"
    ).fetchall()]
    st = {
        "mode": cfg.get("mode"),
        "enabled": cfg.get("enabled") == "true",
        "start_date": cfg.get("start_date"),
        "before_start": before_start(cfg),
        "in_window": ok, "window_reason": why,
        "warmup_day": day, "daily_limit": limit,
        "deliverability_multiplier": mult, "reputation": score,
        "sent_today": sender.sent_today(conn),
        "corpus_remaining": sender.corpus_remaining(conn),
        "reveals_this_month": _reveals_this_month(conn),
        "monthly_enrich_cap": int(cfg.get("monthly_enrich_cap", 90)),
        "test_count": int(cfg.get("test_count", 5)),
        "test_emails": sender.get_test_emails(conn),
        "send_days": cfg.get("send_days", "0,1,2,3,4"),
        "start_hour": int(cfg.get("start_hour", 9)),
        "end_hour": int(cfg.get("end_hour", 17)),
        "cycle_minutes": int(cfg.get("cycle_minutes", 20)),
        "last_cycle_at": cfg.get("last_cycle_at"),
        "learning": learned_peak_hours(conn, cfg),
        "alerts": alerts,
    }
    conn.close()
    return st


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="US outreach orchestrator")
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--daemon", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    if args.init:
        init_db()
    elif args.status:
        print(json.dumps(status(), indent=2, default=str))
    elif args.daemon:
        print("🛰  Orchestrator daemon started.")
        while True:
            try:
                cfg = get_config()
                interval = max(5, int(cfg.get("cycle_minutes", 20))) * 60
                print(f"[{_now_cst().strftime('%a %H:%M CST')}] cycle")
                run_cycle()
                time.sleep(interval)
            except KeyboardInterrupt:
                print("\n   stopped."); break
            except Exception as e:
                print(f"   ❌ {e}"); time.sleep(60)
    else:  # --once (default)
        run_cycle()


if __name__ == "__main__":
    main()
