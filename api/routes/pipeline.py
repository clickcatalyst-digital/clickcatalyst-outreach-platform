# api/routes/pipeline.py
# Pipeline trigger endpoints + Server-Sent Events log streaming

import sys
import io
import queue
import threading
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..database import get_conn

# Lazy imports — pipeline scripts must be in sys.path
# Add your scripts directory to PYTHONPATH before running the API
def _import_pipeline():
    from domain_extractor_01  import run_enrichment_batch
    from pixel_checker_02     import run_pixel_batch
    from competition_intel_03 import run_intelligence_batch
    from email_engine_04      import run_email_batch
    return run_enrichment_batch, run_pixel_batch, run_intelligence_batch, run_email_batch

def _import_email_engine():
    from email_engine_04 import run_email_batch
    return run_email_batch

router = APIRouter()

STAGE_NAMES = {
    1: "Domain Finder",
    2: "Pixel Checker",
    3: "Intelligence Engine",
    4: "Email Dispatch",
}


class PipelineRunRequest(BaseModel):
    stage: int                          # 1-4
    batch_size: int = 50
    max_workers: int = 10
    test_email: Optional[str] = None    # if set, email stage uses test mode


# ---------------------------------------------------------------------------
# LOG CAPTURE — redirects stdout print() to a queue for SSE streaming
# ---------------------------------------------------------------------------

class LogCapture(io.TextIOBase):
    def __init__(self, log_queue: queue.Queue):
        self.q = log_queue

    def write(self, msg: str):
        if msg.strip():
            self.q.put(msg.rstrip())
        return len(msg)

    def flush(self):
        pass


# ---------------------------------------------------------------------------
# STAGE RUNNER (runs in background thread)
# ---------------------------------------------------------------------------

def _run_stage(stage: int, batch_size: int, max_workers: int,
               test_email: Optional[str], log_q: queue.Queue, run_id: int):
    """Runs the requested pipeline stage, capturing all stdout to log_q."""
    original_stdout = sys.stdout
    sys.stdout = LogCapture(log_q)
    conn = get_conn()
    cursor = conn.cursor()
    success = 0
    failed  = 0

    try:
        run_enrichment_batch, run_pixel_batch, run_intelligence_batch, run_email_batch = _import_pipeline()

        if stage == 1:
            run_enrichment_batch(batch_size=batch_size)
        elif stage == 2:
            run_pixel_batch(max_workers=max_workers, batch_size=batch_size)
        elif stage == 3:
            run_intelligence_batch(batch_size=batch_size)
        elif stage == 4:
            run_email_batch(
                recipient_email_override=test_email,
                batch_size=batch_size
            )

        status = "Completed"

    except Exception as e:
        log_q.put(f"❌ FATAL ERROR: {e}")
        status = "Failed"
        failed = 1

    finally:
        sys.stdout = original_stdout
        log_q.put(None)  # sentinel — signals stream end

        cursor.execute("""
            UPDATE pipeline_runs
            SET Finished_At = ?, Status = ?
            WHERE Run_ID = ?
        """, (datetime.utcnow().isoformat(), status, run_id))
        conn.commit()
        conn.close()


# ---------------------------------------------------------------------------
# ENDPOINTS
# ---------------------------------------------------------------------------

@router.post("/run")
def trigger_stage(req: PipelineRunRequest):
    """
    Triggers a pipeline stage.
    Returns run_id — client then connects to /stream/{run_id} for live logs.
    """
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO pipeline_runs (Stage, Stage_Name, Batch_Size, Status)
        VALUES (?, ?, ?, 'Running')
    """, (req.stage, STAGE_NAMES.get(req.stage, f"Stage {req.stage}"), req.batch_size))
    conn.commit()
    run_id = cursor.lastrowid
    conn.close()

    log_q: queue.Queue = queue.Queue()

    thread = threading.Thread(
        target=_run_stage,
        args=(req.stage, req.batch_size, req.max_workers, req.test_email, log_q, run_id),
        daemon=True
    )
    thread.start()

    # Store queue reference so /stream can access it
    _active_runs[run_id] = log_q
    return {"run_id": run_id}


_active_runs: dict[int, queue.Queue] = {}


@router.get("/stream/{run_id}")
def stream_logs(run_id: int):
    """
    SSE endpoint — streams log lines for a given run_id.
    Client receives text/event-stream.
    """
    def event_generator():
        log_q = _active_runs.get(run_id)
        if not log_q:
            yield f"data: {json.dumps({'line': 'Run not found or already finished.'})}\n\n"
            return

        while True:
            try:
                line = log_q.get(timeout=60)
                if line is None:  # sentinel
                    yield f"data: {json.dumps({'line': '__DONE__'})}\n\n"
                    _active_runs.pop(run_id, None)
                    break
                yield f"data: {json.dumps({'line': line})}\n\n"
            except queue.Empty:
                yield f"data: {json.dumps({'line': '__TIMEOUT__'})}\n\n"
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/history")
def get_run_history(limit: int = 50):
    """Returns past pipeline runs."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT Run_ID, Stage, Stage_Name, Batch_Size,
               Started_At, Finished_At, Status,
               Success_Count, Failed_Count
        FROM pipeline_runs
        ORDER BY Run_ID DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


@router.get("/status")
def get_pipeline_status(country: Optional[str] = None):
    """Returns counts for each pipeline stage for the status bar."""
    from ..database import country_filter
    conn = get_conn()
    cursor = conn.cursor()
    # Scope company_enrichment by country via CIN prefix.
    ef = country_filter(country, "CIN")           # ' AND CIN LIKE/NOT LIKE APOLLO_%'
    cf = country_filter(country, "cc.CIN")

    def count(query):
        cursor.execute(query)
        return cursor.fetchone()[0]

    # total_qualified: India = MCA view; US = Apollo company_enrichment rows.
    if (country or "").lower() == "us":
        total_qualified = count("SELECT COUNT(*) FROM company_enrichment WHERE Lead_Source = 'US_Apollo'")
    elif (country or "").lower() == "india":
        total_qualified = count("SELECT COUNT(*) FROM vw_qualified_leads")
    else:
        total_qualified = count("SELECT COUNT(*) FROM vw_qualified_leads")

    data = {
        "total_qualified":      total_qualified,
        "enriched":             count(f"SELECT COUNT(*) FROM company_enrichment WHERE Website_URL IS NOT NULL {ef}"),
        "pixel_confirmed":      count(f"SELECT COUNT(*) FROM company_enrichment WHERE Has_Google_Ads_Pixel = 1 {ef}"),
        "intelligence_ready":   count(f"SELECT COUNT(*) FROM company_enrichment WHERE Pipeline_Status = 'Intelligence_Ready' {ef}"),
        "outreach_sent":        count(f"SELECT COUNT(*) FROM company_enrichment WHERE Pipeline_Status = 'Outreach_Sent' {ef}"),
        "contacts_added":       count(f"SELECT COUNT(DISTINCT cc.CIN) FROM company_contacts cc WHERE 1=1 {cf}"),
        "failed":               count(f"SELECT COUNT(*) FROM company_enrichment WHERE Domain_Source = 'Failed / Not Found' {ef}"),
        "max_retries_reached":  count(f"SELECT COUNT(*) FROM company_enrichment WHERE Enrichment_Attempts >= 5 AND (Website_URL IS NULL OR Website_URL = '') {ef}"),
        "unsubscribed":         count(f"SELECT COUNT(*) FROM company_enrichment WHERE Unsubscribed = 1 {ef}"),
        "hard_bounced":         count(f"SELECT COUNT(*) FROM company_enrichment WHERE Pipeline_Status = 'Hard_Bounce' {ef}"),
    }
    conn.close()
    return data


@router.get("/scheduler/status")
def get_scheduler_status():
    """Returns current scheduling state."""
    import datetime as dt
    conn = get_conn()
    cursor = conn.cursor()

    # Warmup day
    cursor.execute("SELECT MIN(Email_Sent_Date) FROM outreach_analytics")
    first_send = cursor.fetchone()[0]
    warmup_day = 0
    if first_send:
        first_date = dt.date.fromisoformat(first_send)
        warmup_day = (dt.date.today() - first_date).days

    # Daily limit
    schedule = [(0,3,5),(4,7,10),(8,14,20),(15,21,35),(22,30,50),(31,60,75),(61,999,100)]
    daily_limit = 5
    for start, end, limit in schedule:
        if start <= warmup_day <= end:
            daily_limit = limit
            break

    cursor.execute("SELECT COUNT(*) FROM outreach_analytics WHERE Email_Sent_Date = date('now')")
    sent_today = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM outreach_analytics WHERE Email_Sent_Date >= date('now', '-7 days')")
    sent_week = cursor.fetchone()[0]

    # Queue
    cursor.execute("""
        SELECT COUNT(*) FROM vw_qualified_leads q
        JOIN company_enrichment e ON q.CIN = e.CIN
        JOIN company_contacts cc ON q.CIN = cc.CIN AND cc.Is_Primary_Contact = 1
        WHERE e.Pipeline_Status = 'Intelligence_Ready'
        AND (e.Unsubscribed IS NULL OR e.Unsubscribed = 0)
    """)
    queue_size = cursor.fetchone()[0]

    # Next up preview
    cursor.execute("""
        SELECT q.CIN, q.CompanyName, q.State, q.PaidupCapital, cc.Email_Address
        FROM vw_qualified_leads q
        JOIN company_enrichment e ON q.CIN = e.CIN
        JOIN company_contacts cc ON q.CIN = cc.CIN AND cc.Is_Primary_Contact = 1
        WHERE e.Pipeline_Status = 'Intelligence_Ready'
        AND (e.Unsubscribed IS NULL OR e.Unsubscribed = 0)
        ORDER BY q.PaidupCapital DESC
        LIMIT 10
    """)
    next_up = [dict(r) for r in cursor.fetchall()]

    # By hour performance
    cursor.execute("""
        SELECT Send_Hour, COUNT(*) as sent,
            SUM(CASE WHEN Email_Opened = 1 THEN 1 ELSE 0 END) as opened,
            SUM(CASE WHEN Audit_Link_Clicked = 1 THEN 1 ELSE 0 END) as clicked,
            SUM(CASE WHEN Reply_Received = 1 THEN 1 ELSE 0 END) as replied
        FROM outreach_analytics WHERE Send_Hour IS NOT NULL
        GROUP BY Send_Hour ORDER BY Send_Hour
    """)
    by_hour = [dict(r) for r in cursor.fetchall()]

    # By day performance
    cursor.execute("""
        SELECT Send_DayOfWeek, COUNT(*) as sent,
            SUM(CASE WHEN Email_Opened = 1 THEN 1 ELSE 0 END) as opened,
            SUM(CASE WHEN Audit_Link_Clicked = 1 THEN 1 ELSE 0 END) as clicked,
            SUM(CASE WHEN Reply_Received = 1 THEN 1 ELSE 0 END) as replied
        FROM outreach_analytics WHERE Send_DayOfWeek IS NOT NULL
        GROUP BY Send_DayOfWeek ORDER BY Send_DayOfWeek
    """)
    by_day = [dict(r) for r in cursor.fetchall()]

    # Schedule config
    cursor.execute("SELECT Config_Key, Config_Value FROM scheduler_config")
    config = {row[0]: row[1] for row in cursor.fetchall()}

    now = dt.datetime.now()
    hour = now.hour
    dow = now.weekday()

    start_h = int(config.get('start_hour', '9'))
    end_h = int(config.get('end_hour', '17'))
    peak = [int(x) for x in config.get('peak_hours', '10,11,14,15').split(',') if x.strip()]
    send_days = [int(x) for x in config.get('send_days', '0,1,2,3,4').split(',') if x.strip()]

    is_send_day = dow in send_days
    is_business_hours = start_h <= hour < end_h
    is_peak = hour in peak

    conn.close()

    return {
        "warmup_day": warmup_day,
        "daily_limit": daily_limit,
        "sent_today": sent_today,
        "sent_week": sent_week,
        "remaining": max(0, daily_limit - sent_today),
        "queue_size": queue_size,
        "next_up": next_up,
        "current_hour": hour,
        "current_day": dow,
        "is_weekend": not is_send_day,
        "is_business_hours": is_business_hours,
        "is_peak": is_peak,
        "can_send": is_business_hours and is_send_day and sent_today < daily_limit and queue_size > 0,
        "config": {
            "start_hour": start_h,
            "end_hour": end_h,
            "peak_hours": peak,
            "send_days": send_days,
        },
        "by_hour": by_hour,
        "by_day": by_day,
    }


@router.post("/scheduler/send")
def execute_scheduled_send(req: dict = {}):
    """
    Triggers a warmup-aware send batch — replaces `python send_scheduler.py --execute`.
    Respects daily limits, business hours, and optional Bayesian volume adjustment.
    """
    import datetime as dt
    conn = get_conn()
    cursor = conn.cursor()

    now = dt.datetime.now()
    cursor.execute("SELECT Config_Key, Config_Value FROM scheduler_config")
    config = {row[0]: row[1] for row in cursor.fetchall()}
    send_days = [int(x) for x in config.get('send_days', '0,1,2,3,4').split(',') if x.strip()]
    start_h = int(config.get('start_hour', '9'))
    end_h = int(config.get('end_hour', '17'))

    if now.weekday() not in send_days:
        day_names = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
        return {"error": f"{day_names[now.weekday()]} is not a send day", "sent": 0}
    if now.hour < start_h or now.hour >= end_h:
        return {"error": f"Outside send hours ({now.hour}:00, window is {start_h}:00–{end_h}:00)", "sent": 0}

    # Calculate remaining
    cursor.execute("SELECT MIN(Email_Sent_Date) FROM outreach_analytics")
    first_send = cursor.fetchone()[0]
    warmup_day = 0
    if first_send:
        warmup_day = (dt.date.today() - dt.date.fromisoformat(first_send)).days

    schedule = [(0,3,5),(4,7,10),(8,14,20),(15,21,35),(22,30,50),(31,60,75),(61,999,100)]
    daily_limit = 5
    for start, end, limit in schedule:
        if start <= warmup_day <= end:
            daily_limit = limit
            break

    cursor.execute("SELECT COUNT(*) FROM outreach_analytics WHERE Email_Sent_Date = date('now')")
    sent_today = cursor.fetchone()[0]
    remaining = max(0, daily_limit - sent_today)
    conn.close()

    if remaining == 0:
        return {"error": "Daily limit reached", "sent": 0, "daily_limit": daily_limit}

    # Override with custom count if provided (but cap at remaining)
    custom_count = req.get("count")
    if custom_count:
        remaining = min(int(custom_count), remaining)

    test_email = req.get("test_email")

    # Trigger Stage 4 via the existing pipeline mechanism
    from ..database import get_conn as get_db
    import queue, threading

    conn2 = get_db()
    cursor2 = conn2.cursor()
    cursor2.execute("""
        INSERT INTO pipeline_runs (Stage, Stage_Name, Batch_Size, Status)
        VALUES (4, 'Scheduled Send', ?, 'Running')
    """, (remaining,))
    conn2.commit()
    run_id = cursor2.lastrowid
    conn2.close()

    log_q = queue.Queue()

    def _run():
        import sys, io
        original = sys.stdout
        class Capture(io.TextIOBase):
            def write(self, msg):
                if msg.strip(): log_q.put(msg.rstrip())
                return len(msg)
        sys.stdout = Capture()
        try:
            run_fn = _import_email_engine()
            run_fn(recipient_email_override=test_email, batch_size=remaining)
            status = "Completed"
        except Exception as e:
            log_q.put(f"❌ ERROR: {e}")
            status = "Failed"
        finally:
            sys.stdout = original
            log_q.put(None)
            c = get_db()
            c.cursor().execute(
                "UPDATE pipeline_runs SET Finished_At = ?, Status = ? WHERE Run_ID = ?",
                (dt.datetime.utcnow().isoformat(), status, run_id)
            )
            c.commit()
            c.close()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    _active_runs[run_id] = log_q

    return {
        "ok": True,
        "run_id": run_id,
        "batch_size": remaining,
        "test_mode": bool(test_email),
        "daily_limit": daily_limit,
        "warmup_day": warmup_day,
    }


@router.get("/scheduler/week-plan")
def get_week_plan():
    """Projected send volumes for the next 7 days — replaces `python send_scheduler.py --plan-week`"""
    import datetime as dt
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("SELECT MIN(Email_Sent_Date) FROM outreach_analytics")
    first_send = cursor.fetchone()[0]
    warmup_day = 0
    if first_send:
        warmup_day = (dt.date.today() - dt.date.fromisoformat(first_send)).days

    schedule = [(0,3,5),(4,7,10),(8,14,20),(15,21,35),(22,30,50),(31,60,75),(61,999,100)]

    cursor.execute("SELECT COUNT(*) FROM outreach_analytics WHERE Email_Sent_Date = date('now')")
    sent_today = cursor.fetchone()[0]

    cursor.execute("SELECT Config_Key, Config_Value FROM scheduler_config")
    config = {row[0]: row[1] for row in cursor.fetchall()}
    send_days = [int(x) for x in config.get('send_days', '0,1,2,3,4').split(',') if x.strip()]

    conn.close()

    days = []
    day_names = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
    total = 0

    for i in range(7):
        d = dt.date.today() + dt.timedelta(days=i)
        dow = d.weekday()
        projected_warmup = warmup_day + i

        limit = 5
        for start, end, lim in schedule:
            if start <= projected_warmup <= end:
                limit = lim
                break

        is_weekend = dow not in send_days
        sends = 0 if is_weekend else limit
        if i == 0:
            sends = max(0, limit - sent_today)
        total += sends

        days.append({
            "date": d.isoformat(),
            "day_name": day_names[dow],
            "warmup_day": projected_warmup,
            "daily_limit": limit,
            "projected_sends": sends,
            "is_weekend": is_weekend,
            "is_today": i == 0,
        })

    return {"days": days, "total_projected": total, "current_warmup_day": warmup_day}


@router.get("/scheduler/config")
def get_scheduler_config():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT Config_Key, Config_Value FROM scheduler_config")
    config = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    return config


@router.patch("/scheduler/config")
def update_scheduler_config(body: dict):
    allowed = ['start_hour', 'end_hour', 'peak_hours', 'avoid_hours', 'send_days', 'warmup_override']
    conn = get_conn()
    cursor = conn.cursor()
    updated = []
    for key, value in body.items():
        if key in allowed:
            cursor.execute("""
                INSERT INTO scheduler_config (Config_Key, Config_Value, Updated_At)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(Config_Key) DO UPDATE SET Config_Value = ?, Updated_At = CURRENT_TIMESTAMP
            """, (key, str(value), str(value)))
            updated.append(key)
    conn.commit()
    conn.close()
    return {"ok": True, "updated": updated}


@router.get("/preview-next-email")
def preview_next_email(test_email: str = ""):
    """Renders a full preview of the next email that would be sent."""
    import datetime as dt
    conn = get_conn()
    cursor = conn.cursor()

    # Get next lead in queue
    cursor.execute("""
        SELECT
            q.CIN, q.CompanyName, q.nic_code,
            e.Personalized_Sentence, e.Competitor_Count, e.Has_GMB, e.Website_URL,
            cc.Email_Address, cc.Full_Name
        FROM vw_qualified_leads q
        JOIN company_enrichment e ON q.CIN = e.CIN
        JOIN company_contacts cc ON q.CIN = cc.CIN AND cc.Is_Primary_Contact = 1
        WHERE e.Pipeline_Status = 'Intelligence_Ready'
        AND (e.Unsubscribed IS NULL OR e.Unsubscribed = 0)
        ORDER BY q.PaidupCapital DESC
        LIMIT 1
    """)
    row = cursor.fetchone()

    if not row:
        conn.close()
        return {"error": "No leads in queue", "has_preview": False}

    lead = dict(row)
    cin = lead['CIN']
    company_name = lead['CompanyName'].title() if lead['CompanyName'] else 'Unknown'
    sentence = lead['Personalized_Sentence'] or ''

    # Determine variant
    try:
        from campaign_engine import get_campaign_variant, get_ab_variant
        lead_info = {'nic_code': lead['nic_code'], 'Competitor_Count': lead['Competitor_Count'], 'Has_GMB': lead['Has_GMB']}
        variant_base = get_campaign_variant(lead_info)
        try:
            from bayesian_engine import select_variant_thompson
            variant_key = select_variant_thompson(variant_base, cin)
        except ImportError:
            variant_key = get_ab_variant(cin, variant_base)
    except ImportError:
        variant_key = 'generic_audit_v1_a'

    # Fetch template
    cursor.execute(
        "SELECT * FROM campaign_templates WHERE Variant_Key = ? AND Is_Active = 1",
        (variant_key,)
    )
    tmpl = cursor.fetchone()
    conn.close()

    # Build preview URLs
    batch_id = f"batch_{dt.date.today().isoformat().replace('-', '_')}"
    audit_url = f"https://clickcatalyst.digital/free-audit?utm_source=coldemail&utm_medium=outreach&utm_campaign={batch_id}&cin={cin}"
    tracking_pixel_url = "[tracking pixel]"
    unsubscribe_url = f"https://clickcatalyst.digital/api/unsubscribe?cin={cin}"

    if tmpl:
        tmpl = dict(tmpl)
        variables = {
            'company_name': company_name,
            'personalized_sentence': sentence,
            'audit_url': audit_url,
            'competitor_count': str(lead['Competitor_Count'] or 0),
            'tracking_pixel_url': tracking_pixel_url,
            'unsubscribe_url': unsubscribe_url,
        }
        html = tmpl['Body_HTML']
        plain = tmpl['Body_Plain']
        subject = tmpl['Subject_Line']
        for k, v in variables.items():
            html = html.replace('{' + k + '}', v)
            plain = plain.replace('{' + k + '}', v)
            subject = subject.replace('{' + k + '}', v)
    else:
        subject = f"Google Ads audit — {company_name}"
        html = f"<p>Template {variant_key} not found — would use fallback</p>"
        plain = f"Template {variant_key} not found"

    return {
        "has_preview": True,
        "cin": cin,
        "company_name": company_name,
        "recipient": test_email or lead['Email_Address'],
        "contact_name": lead['Full_Name'],
        "variant_key": variant_key,
        "subject": subject,
        "body_html": html,
        "body_plain": plain,
        "website": lead['Website_URL'],
        "competitor_count": lead['Competitor_Count'],
        "personalized_sentence": sentence,
    }