# us_lead_engine/sender.py
# Dedicated US-agency email sender. Independent of the MCA scatter-plot engine.
#
# Reads exported US leads (Lead_Source='US_Apollo') from the main DB, picks an arm
# from campaign_templates via Thompson sampling, injects a per-lead personalized
# line, and sends the problem-first agency pitch (reply-for-audit CTA, NO link).
# Logs to outreach_analytics so existing tracking / reply / dashboard infra works.
#
# Test sends use Batch_ID prefix 'ustest' and are EXCLUDED from all prod warmup /
# sent-today math, so flipping test->prod resumes exactly where prod left off.

import os
import sqlite3
import smtplib
import ssl
import time
import random
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .config import MAIN_DB_PATH, DB_PATH as US_LEADS_DB
from .personalization import build_personalized_line
import db_factory

SENDER_EMAIL = os.getenv("SENDER_EMAIL", "")
SENDER_PASS  = os.getenv("SENDER_APP_PASS", "")
SENDER_NAME  = os.getenv("US_FROM_NAME", "Pujan from ClickCatalyst")

POSTAL_ADDRESS = os.getenv("US_POSTAL_ADDRESS", "[SET US_POSTAL_ADDRESS env var]")

TRACK_BASE = "https://clickcatalyst.digital/api/track"
UNSUB_BASE = "https://clickcatalyst.digital/api/unsubscribe"

WARMUP = [(0, 3, 5), (4, 7, 10), (8, 14, 20), (15, 21, 35),
          (22, 30, 50), (31, 60, 75), (61, 999, 100)]

VARIANT_BASE = "us_agency_waste_v1"
PROD_BATCH = "us"
TEST_BATCH = "ustest"   # excluded from prod warmup/volume math


def _conn():
    # Main shared DB: Turso when TURSO_URL/TURSO_AUTH_TOKEN are set, else local SQLite.
    # (us_leads.db corpus connection in _signals_for stays on raw sqlite3 — Mac-only.)
    return db_factory.connect(MAIN_DB_PATH)


def _ensure_columns(conn):
    for ddl in (
        "ALTER TABLE company_enrichment ADD COLUMN Company_Name TEXT",
        "ALTER TABLE company_enrichment ADD COLUMN Lead_Source TEXT",
    ):
        try:
            conn.execute(ddl)
        except Exception:
            # Column already exists: raw sqlite3 raises OperationalError, libsql/Turso
            # raises its own error type. Both mean "nothing to add" — ignore.
            pass


# ---------------------------------------------------------------------------
# VARIANT SELECTION + SIGNALS
# ---------------------------------------------------------------------------

def _select_variant(cin):
    try:
        from bayesian_engine import select_variant_thompson
        return select_variant_thompson(VARIANT_BASE, cin)
    except Exception:
        bucket = sum(ord(c) for c in cin) % 2
        return f"{VARIANT_BASE}_a" if bucket == 0 else f"{VARIANT_BASE}_b"


def _signals_for(cin):
    pid = cin.replace("APOLLO_", "", 1)
    try:
        uc = sqlite3.connect(US_LEADS_DB)
        uc.row_factory = sqlite3.Row
        row = uc.execute(
            "SELECT Org_Employee_Count, City, Org_Industry FROM us_leads WHERE Apollo_Person_ID = ?",
            (pid,),
        ).fetchone()
        uc.close()
        return dict(row) if row else {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# FOOTER
# ---------------------------------------------------------------------------

def _footer_html(unsub_url, pixel_url):
    return (f'<hr style="border:none;border-top:1px solid #eee;margin-top:28px;"/>'
            f'<p style="font-size:11px;color:#aaa;">ClickCatalyst · {POSTAL_ADDRESS}<br/>'
            f'You received this because you run a marketing agency. '
            f'<a href="{unsub_url}" style="color:#aaa;">Unsubscribe</a>.</p>'
            f'<img src="{pixel_url}" width="1" height="1" alt="" style="display:block;"/>')


def _footer_plain(unsub_url):
    return f"\n\n---\nClickCatalyst · {POSTAL_ADDRESS}\nUnsubscribe: {unsub_url}\n"


# ---------------------------------------------------------------------------
# WARMUP / CORPUS / TEST-EMAILS  (prod math excludes test batches)
# ---------------------------------------------------------------------------

def warmup_limit(conn):
    row = conn.execute(f"""
        SELECT MIN(oa.Email_Sent_Date)
        FROM outreach_analytics oa
        JOIN company_enrichment e ON oa.CIN = e.CIN
        WHERE e.Lead_Source = 'US_Apollo' AND oa.Batch_ID NOT LIKE '{TEST_BATCH}%'
    """).fetchone()
    first = row[0]
    day = (date.today() - date.fromisoformat(first)).days if first else 0
    for start, end, limit in WARMUP:
        if start <= day <= end:
            return limit, day
    return 5, day


def sent_today(conn):
    return conn.execute(f"""
        SELECT COUNT(*) FROM outreach_analytics oa
        JOIN company_enrichment e ON oa.CIN = e.CIN
        WHERE e.Lead_Source = 'US_Apollo'
          AND oa.Email_Sent_Date = date('now')
          AND oa.Batch_ID NOT LIKE '{TEST_BATCH}%'
    """).fetchone()[0]


def corpus_remaining(conn):
    """Unsent, send-ready US leads (the prod queue)."""
    return conn.execute("""
        SELECT COUNT(*) FROM company_enrichment e
        JOIN company_contacts cc ON e.CIN = cc.CIN AND cc.Is_Primary_Contact = 1
        WHERE e.Lead_Source = 'US_Apollo'
          AND e.Pipeline_Status = 'Intelligence_Ready'
          AND (e.Unsubscribed IS NULL OR e.Unsubscribed = 0)
          AND (cc.Email_Label IS NULL OR cc.Email_Label != 'Bounced')
    """).fetchone()[0]


def fetch_sendable(conn, limit):
    """Next N unsent send-ready US leads (corpus order: highest capital-equivalent first)."""
    return conn.execute("""
        SELECT e.CIN, e.Company_Name, cc.Full_Name, cc.Email_Address
        FROM company_enrichment e
        JOIN company_contacts cc ON e.CIN = cc.CIN AND cc.Is_Primary_Contact = 1
        WHERE e.Lead_Source = 'US_Apollo'
          AND e.Pipeline_Status = 'Intelligence_Ready'
          AND (e.Unsubscribed IS NULL OR e.Unsubscribed = 0)
          AND (cc.Email_Label IS NULL OR cc.Email_Label != 'Bounced')
        ORDER BY e.CIN
        LIMIT ?
    """, (limit,)).fetchall()


def get_test_emails(conn):
    try:
        rows = conn.execute("SELECT Email FROM us_test_emails ORDER BY ID").fetchall()
        return [r[0] for r in rows]
    except sqlite3.OperationalError:
        return []


# ---------------------------------------------------------------------------
# SEND ONE
# ---------------------------------------------------------------------------

def send_one(conn, lead, test_email=None, dry_run=False, batch_prefix=PROD_BATCH):
    cin = lead["CIN"]
    company = lead["Company_Name"] or "your agency"
    first = (lead["Full_Name"] or "").split(" ")[0] or "there"
    recipient = test_email or lead["Email_Address"]
    if not recipient:
        return False, "no recipient"

    variant = _select_variant(cin)
    cur = conn.cursor()
    tmpl = cur.execute(
        "SELECT Subject_Line, Body_HTML, Body_Plain FROM campaign_templates WHERE Variant_Key = ? AND Is_Active = 1",
        (variant,),
    ).fetchone()
    if not tmpl:
        return False, f"template '{variant}' not found — run: python -m us_lead_engine.seed_campaigns"

    sig = _signals_for(cin)
    pline = build_personalized_line(sig.get("Org_Employee_Count"), sig.get("City"), sig.get("Org_Industry"))

    now = datetime.now()
    batch_id = f"{batch_prefix}_{date.today().isoformat().replace('-', '_')}"
    cur.execute("""
        INSERT INTO outreach_analytics
            (CIN, Email_Sent_Date, Batch_ID, Campaign_Variant,
             Subject_Line, Send_Hour, Send_DayOfWeek)
        VALUES (?, date('now'), ?, ?, ?, ?, ?)
    """, (cin, batch_id, variant, tmpl["Subject_Line"], now.hour, now.weekday()))
    conn.commit()
    aid = cur.lastrowid

    pixel_url = f"{TRACK_BASE}/email-open?aid={aid}"
    unsub_url = f"{UNSUB_BASE}?cin={cin}"

    repl = {"first_name": first, "company_name": company, "personalized_line": pline}
    subject, html, plain = tmpl["Subject_Line"], tmpl["Body_HTML"], tmpl["Body_Plain"]
    for k, v in repl.items():
        subject = subject.replace("{" + k + "}", v)
        html = html.replace("{" + k + "}", v)
        plain = plain.replace("{" + k + "}", v)
    html += _footer_html(unsub_url, pixel_url)
    plain += _footer_plain(unsub_url)

    if dry_run:
        print(f"   [dry] → {recipient} | [{variant}] {subject}")
        return True, None

    msg = MIMEMultipart("alternative")
    msg["From"] = f"{SENDER_NAME} <{SENDER_EMAIL}>"
    msg["To"] = recipient
    msg["Subject"] = subject
    msg["Reply-To"] = SENDER_EMAIL
    msg["List-Unsubscribe"] = f"<{unsub_url}>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
            s.login(SENDER_EMAIL, SENDER_PASS)
            s.send_message(msg)
    except Exception as e:
        _handle_bounce(conn, cin, aid, e)
        return False, str(e)

    # Advance prod pipeline ONLY for real prod sends (never test).
    if batch_prefix == PROD_BATCH and not test_email:
        cur.execute("""
            UPDATE company_enrichment
            SET Pipeline_Status = 'Outreach_Sent', Email_Sent_Date = date('now')
            WHERE CIN = ?
        """, (cin,))
        conn.commit()
    return True, None


def _handle_bounce(conn, cin, aid, err):
    msg = str(err).lower()
    hard = any(s in msg for s in (
        "user unknown", "mailbox not found", "recipient rejected", "no such user",
        "does not exist", "invalid recipient", "550", "551", "552", "553", "554"))
    conn.execute("UPDATE outreach_analytics SET Bounced = 1, Send_Error = ? WHERE Analytics_ID = ?",
                 (str(err)[:200], aid))
    if hard:
        conn.execute("UPDATE company_contacts SET Email_Label = 'Bounced' WHERE CIN = ? AND Is_Primary_Contact = 1", (cin,))
        conn.execute("UPDATE company_enrichment SET Pipeline_Status = 'Hard_Bounce', Last_Error = ? WHERE CIN = ?",
                     (f"Hard bounce: {str(err)[:150]}", cin))
    conn.commit()


# ---------------------------------------------------------------------------
# MANUAL RUN (the --send CLI path; orchestrator uses send_one directly)
# ---------------------------------------------------------------------------

def run(count=None, test_email=None, dry_run=False):
    conn = _conn()
    _ensure_columns(conn)
    limit, day = warmup_limit(conn)
    already = sent_today(conn)
    remaining = (count or 1) if test_email else max(0, limit - already)
    if not test_email and count:
        remaining = min(count, remaining)
    if remaining <= 0:
        print(f"   Warmup limit reached (day {day}, limit {limit}, sent today {already}).")
        conn.close(); return

    rows = fetch_sendable(conn, remaining)
    if not rows:
        print("   No US leads ready to send. Run --export first.")
        conn.close(); return

    mode = f" [TEST → {test_email}]" if test_email else ""
    print(f"📧 US sender — warmup day {day}, daily limit {limit}, sending {len(rows)}{mode}")
    if POSTAL_ADDRESS.startswith("["):
        print("   ⚠ US_POSTAL_ADDRESS not set — CAN-SPAM requires a real address before live sends.")

    batch_prefix = TEST_BATCH if test_email else PROD_BATCH
    sent = 0
    for r in rows:
        ok, err = send_one(conn, r, test_email, dry_run, batch_prefix)
        print(f"   {'✅' if ok else '❌'} {test_email or r['Email_Address']} ({r['Company_Name']})"
              + ("" if ok else f" — {err}"))
        sent += 1 if ok else 0
        if not dry_run and not test_email:
            time.sleep(random.uniform(20, 40))
    conn.close()
    print(f"🏁 Sent {sent}/{len(rows)}.")
