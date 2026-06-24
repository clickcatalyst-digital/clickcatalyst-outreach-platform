# api/routes/queue.py
# Queue management endpoints — schedule, monitor, control email dispatch

from fastapi import APIRouter
from ..database import get_conn

router = APIRouter()


@router.get("/status")
def get_queue_status():
    """Current queue state + system health."""
    import datetime as dt
    conn = get_conn()
    cursor = conn.cursor()

    # Queue counts by status
    cursor.execute("""
        SELECT Status, COUNT(*) FROM send_queue GROUP BY Status
    """)
    counts = {row[0]: row[1] for row in cursor.fetchall()}

    # Today's queue activity
    cursor.execute("""
        SELECT COUNT(*) FROM send_queue WHERE Status = 'sent' AND date(Sent_At) = date('now')
    """)
    sent_today_queue = cursor.fetchone()[0]

    # Next 10 queued
    cursor.execute("""
        SELECT sq.Queue_ID, sq.CIN, sq.Variant_Key, sq.Strategy,
               sq.Scheduled_At, sq.Send_After, sq.Test_Email,
               q.CompanyName, cc.Email_Address
        FROM send_queue sq
        LEFT JOIN vw_qualified_leads q ON sq.CIN = q.CIN
        LEFT JOIN company_contacts cc ON sq.CIN = cc.CIN AND cc.Is_Primary_Contact = 1
        WHERE sq.Status = 'queued'
        ORDER BY sq.Scheduled_At ASC
        LIMIT 10
    """)
    upcoming = [dict(r) for r in cursor.fetchall()]

    # Recent sent/failed
    cursor.execute("""
        SELECT sq.Queue_ID, sq.CIN, sq.Variant_Key, sq.Status,
               sq.Sent_At, sq.Error, q.CompanyName
        FROM send_queue sq
        LEFT JOIN vw_qualified_leads q ON sq.CIN = q.CIN
        WHERE sq.Status IN ('sent', 'failed')
        ORDER BY sq.Queue_ID DESC
        LIMIT 10
    """)
    recent = [dict(r) for r in cursor.fetchall()]

    # Config
    cursor.execute("SELECT Config_Key, Config_Value FROM scheduler_config")
    config = {row[0]: row[1] for row in cursor.fetchall()}

    conn.close()

    return {
        "queued": counts.get('queued', 0),
        "sending": counts.get('sending', 0),
        "sent": counts.get('sent', 0),
        "failed": counts.get('failed', 0),
        "sent_today": sent_today_queue,
        "upcoming": upcoming,
        "recent": recent,
        "auto_send_enabled": config.get('auto_send_enabled', 'true') == 'true',
        "strategy": config.get('default_strategy', 'thompson'),
        "force_test_mode": config.get('force_test_mode', 'false') == 'true',
        "test_email_fallback": config.get('test_email_fallback', ''),
        "interval_minutes": int(config.get('send_interval_minutes', '15')),
    }


@router.post("/schedule")
def schedule_batch(body: dict):
    """
    Schedule N emails from the ready queue.
    Body:
      count: int           — how many to schedule
      strategy: str        — 'thompson' | 'even_split' | 'manual'
      variant_key: str     — only used if strategy='manual'
      test_email: str      — override recipient (optional)
      send_after: str      — ISO datetime, delay until this time (optional)
    """
    count = body.get('count', 5)
    strategy = body.get('strategy', '')
    variant_key = body.get('variant_key', '')
    test_email = body.get('test_email', '')
    send_after = body.get('send_after', None)

    conn = get_conn()
    cursor = conn.cursor()

    # Use default strategy if not specified
    if not strategy:
        cursor.execute("SELECT Config_Value FROM scheduler_config WHERE Config_Key = 'default_strategy'")
        row = cursor.fetchone()
        strategy = row[0] if row else 'thompson'

    # Check test mode
    cursor.execute("SELECT Config_Value FROM scheduler_config WHERE Config_Key = 'force_test_mode'")
    row = cursor.fetchone()
    force_test = row and row[0] == 'true'

    if force_test and not test_email:
        cursor.execute("SELECT Config_Value FROM scheduler_config WHERE Config_Key = 'test_email_fallback'")
        row = cursor.fetchone()
        test_email = row[0] if row else ''

    # Get eligible leads (Intelligence_Ready with contacts, not already queued)
    cursor.execute("""
        SELECT q.CIN
        FROM vw_qualified_leads q
        JOIN company_enrichment e ON q.CIN = e.CIN
        JOIN company_contacts cc ON q.CIN = cc.CIN AND cc.Is_Primary_Contact = 1
        WHERE e.Pipeline_Status = 'Intelligence_Ready'
        AND (e.Unsubscribed IS NULL OR e.Unsubscribed = 0)
        AND q.CIN NOT IN (
            SELECT CIN FROM send_queue WHERE Status IN ('queued', 'sending')
        )
        ORDER BY q.PaidupCapital DESC
        LIMIT ?
    """, (count,))
    leads = [row[0] for row in cursor.fetchall()]

    if not leads:
        conn.close()
        return {"ok": False, "error": "No eligible leads found", "scheduled": 0}

    # Insert into queue
    for cin in leads:
        cursor.execute("""
            INSERT INTO send_queue (CIN, Variant_Key, Strategy, Test_Email, Send_After, Created_By)
            VALUES (?, ?, ?, ?, ?, 'ui')
        """, (
            cin,
            variant_key if strategy == 'manual' else None,
            strategy,
            test_email or None,
            send_after
        ))

    conn.commit()
    conn.close()

    return {
        "ok": True,
        "scheduled": len(leads),
        "strategy": strategy,
        "test_mode": bool(test_email),
        "send_after": send_after,
    }


@router.post("/force-send")
def force_send_now(body: dict):
    """
    Immediately send queued emails, bypassing time window checks.
    Body:
      count: int — how many to send now (default: all queued)
    """
    count = body.get('count', 100)

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT Queue_ID, CIN FROM send_queue
        WHERE Status = 'queued'
        ORDER BY Scheduled_At ASC
        LIMIT ?
    """, (count,))
    queued = cursor.fetchall()
    conn.close()

    if not queued:
        return {"ok": False, "error": "No queued emails", "sent": 0}

    # Import and send directly
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    sent = 0
    failed = 0

    for qid, cin in queued:
        try:
            from queue_worker import mark_sending, mark_sent, mark_failed, send_single_email, get_config
            config = get_config()
            mark_sending(qid)
            success, error = send_single_email(
                {'Queue_ID': qid, 'CIN': cin, 'Variant_Key': None, 'Strategy': None, 'Test_Email': None},
                config
            )
            if success:
                mark_sent(qid)
                sent += 1
            else:
                mark_failed(qid, error)
                failed += 1
        except Exception as e:
            failed += 1

        import time, random
        time.sleep(random.uniform(2, 4))

    return {"ok": True, "sent": sent, "failed": failed}


@router.post("/pause")
def pause_auto_send():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO scheduler_config (Config_Key, Config_Value, Updated_At)
        VALUES ('auto_send_enabled', 'false', CURRENT_TIMESTAMP)
        ON CONFLICT(Config_Key) DO UPDATE SET Config_Value = 'false', Updated_At = CURRENT_TIMESTAMP
    """)
    conn.commit()
    conn.close()
    return {"ok": True, "auto_send": False}


@router.post("/resume")
def resume_auto_send():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO scheduler_config (Config_Key, Config_Value, Updated_At)
        VALUES ('auto_send_enabled', 'true', CURRENT_TIMESTAMP)
        ON CONFLICT(Config_Key) DO UPDATE SET Config_Value = 'true', Updated_At = CURRENT_TIMESTAMP
    """)
    conn.commit()
    conn.close()
    return {"ok": True, "auto_send": True}


@router.patch("/config")
def update_queue_config(body: dict):
    """Update queue-related config: strategy, test mode, interval, test email."""
    allowed = ['default_strategy', 'force_test_mode', 'test_email_fallback', 'send_interval_minutes']
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


@router.delete("/clear-failed")
def clear_failed():
    """Remove failed items from queue."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM send_queue WHERE Status = 'failed'")
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return {"ok": True, "deleted": deleted}


@router.delete("/cancel-queued")
def cancel_queued():
    """Cancel all queued (unsent) items."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM send_queue WHERE Status = 'queued'")
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return {"ok": True, "cancelled": deleted}


@router.get("/calendar")
def get_calendar_data(days: int = 14):
    """
    Returns email data grouped by date and hour for calendar view.
    Includes both queued (future) and sent (past) emails.
    """
    import datetime as dt
    conn = get_conn()
    cursor = conn.cursor()
 
    # Sent emails by date and hour (past)
    cursor.execute("""
        SELECT
            oa.Email_Sent_Date as date,
            oa.Send_Hour as hour,
            oa.CIN,
            q.CompanyName,
            oa.Campaign_Variant,
            oa.Subject_Line,
            oa.Email_Opened,
            oa.Audit_Link_Clicked,
            oa.Reply_Received,
            oa.Bounced,
            cc.Email_Address
        FROM outreach_analytics oa
        LEFT JOIN vw_qualified_leads q ON oa.CIN = q.CIN
        LEFT JOIN company_contacts cc ON oa.CIN = cc.CIN AND cc.Is_Primary_Contact = 1
        WHERE oa.Email_Sent_Date >= date('now', ? || ' days')
        ORDER BY oa.Email_Sent_Date DESC, oa.Send_Hour ASC
    """, (f"-{days}",))
    sent_rows = [dict(r) for r in cursor.fetchall()]
 
    # Queued emails (future)
    cursor.execute("""
        SELECT
            sq.Queue_ID,
            sq.CIN,
            sq.Variant_Key,
            sq.Strategy,
            sq.Status,
            sq.Scheduled_At,
            sq.Send_After,
            sq.Test_Email,
            q.CompanyName,
            cc.Email_Address
        FROM send_queue sq
        LEFT JOIN vw_qualified_leads q ON sq.CIN = q.CIN
        LEFT JOIN company_contacts cc ON sq.CIN = cc.CIN AND cc.Is_Primary_Contact = 1
        WHERE sq.Status IN ('queued', 'sending')
        ORDER BY sq.Scheduled_At ASC
    """)
    queued_rows = [dict(r) for r in cursor.fetchall()]
 
    # Aggregate sent by date
    sent_by_date = {}
    for r in sent_rows:
        d = r['date']
        if d not in sent_by_date:
            sent_by_date[d] = {'date': d, 'sent': 0, 'opened': 0, 'clicked': 0, 'replied': 0, 'bounced': 0, 'emails': []}
        sent_by_date[d]['sent'] += 1
        sent_by_date[d]['opened'] += 1 if r['Email_Opened'] else 0
        sent_by_date[d]['clicked'] += 1 if r['Audit_Link_Clicked'] else 0
        sent_by_date[d]['replied'] += 1 if r['Reply_Received'] else 0
        sent_by_date[d]['bounced'] += 1 if r['Bounced'] else 0
        sent_by_date[d]['emails'].append({
            'cin': r['CIN'],
            'company': r['CompanyName'],
            'variant': r['Campaign_Variant'],
            'subject': r['Subject_Line'],
            'hour': r['hour'],
            'email': r['Email_Address'],
            'opened': bool(r['Email_Opened']),
            'clicked': bool(r['Audit_Link_Clicked']),
            'replied': bool(r['Reply_Received']),
            'bounced': bool(r['Bounced']),
            'status': 'sent',
        })
 
    # Aggregate queued by date
    today = dt.date.today().isoformat()
    if today not in sent_by_date:
        sent_by_date[today] = {'date': today, 'sent': 0, 'opened': 0, 'clicked': 0, 'replied': 0, 'bounced': 0, 'emails': []}
 
    for r in queued_rows:
        target_date = today
        if r['Send_After']:
            try:
                target_date = r['Send_After'][:10]
            except:
                pass
        if target_date not in sent_by_date:
            sent_by_date[target_date] = {'date': target_date, 'sent': 0, 'opened': 0, 'clicked': 0, 'replied': 0, 'bounced': 0, 'emails': []}
        sent_by_date[target_date]['emails'].append({
            'cin': r['CIN'],
            'company': r['CompanyName'],
            'variant': r['Variant_Key'] or 'auto',
            'subject': None,
            'hour': None,
            'email': r['Test_Email'] or r['Email_Address'],
            'opened': False,
            'clicked': False,
            'replied': False,
            'bounced': False,
            'status': r['Status'],
        })
 
    # Build sorted list
    calendar = sorted(sent_by_date.values(), key=lambda x: x['date'], reverse=True)
 
    conn.close()
    return {"days": calendar, "total_queued": len(queued_rows)}