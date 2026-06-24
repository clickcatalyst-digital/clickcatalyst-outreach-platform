#!/usr/bin/env python3
"""
queue_worker.py

Background daemon that processes the send_queue table.
Checks every N minutes (configurable). During send windows,
picks queued emails, selects variants, and dispatches.

Usage:
    python queue_worker.py              # run once (process current queue)
    python queue_worker.py --daemon     # run continuously
    python queue_worker.py --status     # show queue stats

Architecture:
    UI schedules emails → send_queue table → this worker sends them
    Worker reads scheduler_config for hours, days, limits, strategy.
    Worker respects warmup ramp and Bayesian volume adjustment.
"""

import sqlite3
import os
import sys
import time
import json
import argparse
from datetime import datetime, date, timedelta

DB_PATH = os.getenv(
    'DB_PATH',
    '/Users/pujan/Developer/data_collector/indian_companies/company_master_data.db'
)


# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

def get_config():
    """Read all scheduler config from DB."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT Config_Key, Config_Value FROM scheduler_config")
    config = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    return config


def get_warmup_limit():
    """Calculate daily send limit based on warmup phase."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT MIN(Email_Sent_Date) FROM outreach_analytics")
    first_send = cursor.fetchone()[0]
    conn.close()

    warmup_day = 0
    if first_send:
        first_date = date.fromisoformat(first_send)
        warmup_day = (date.today() - first_date).days

    schedule = [(0,3,5),(4,7,10),(8,14,20),(15,21,35),(22,30,50),(31,60,75),(61,999,100)]
    for start, end, limit in schedule:
        if start <= warmup_day <= end:
            return limit, warmup_day
    return 5, warmup_day


def get_sent_today():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM outreach_analytics WHERE Email_Sent_Date = date('now')")
    count = cursor.fetchone()[0]
    conn.close()
    return count


# ---------------------------------------------------------------------------
# SEND WINDOW CHECK
# ---------------------------------------------------------------------------

def is_send_window(config):
    """Check if right now is within the configured send window."""
    now = datetime.now()
    hour = now.hour
    dow = now.weekday()

    start_h = int(config.get('start_hour', '9'))
    end_h = int(config.get('end_hour', '17'))
    send_days = [int(x) for x in config.get('send_days', '0,1,2,3,4').split(',') if x.strip()]

    if dow not in send_days:
        return False, f"Not a send day ({['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][dow]})"
    if hour < start_h or hour >= end_h:
        return False, f"Outside send hours ({hour}:00, window: {start_h}:00-{end_h}:00)"
    return True, "In send window"


def is_peak_hour(config):
    """Check if current hour is a peak hour."""
    peak = [int(x) for x in config.get('peak_hours', '10,11,14,15').split(',') if x.strip()]
    return datetime.now().hour in peak


# ---------------------------------------------------------------------------
# QUEUE PROCESSING
# ---------------------------------------------------------------------------

def get_queued_emails(limit):
    """Get emails ready to send from the queue."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    cursor.execute("""
        SELECT Queue_ID, CIN, Variant_Key, Strategy, Test_Email
        FROM send_queue
        WHERE Status = 'queued'
        AND (Send_After IS NULL OR Send_After <= ?)
        ORDER BY Scheduled_At ASC
        LIMIT ?
    """, (now, limit))

    rows = [dict(zip(['Queue_ID', 'CIN', 'Variant_Key', 'Strategy', 'Test_Email'],
                      row)) for row in cursor.fetchall()]
    conn.close()
    return rows


def mark_sending(queue_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE send_queue SET Status = 'sending' WHERE Queue_ID = ?", (queue_id,))
    conn.commit()
    conn.close()


def mark_sent(queue_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE send_queue SET Status = 'sent', Sent_At = CURRENT_TIMESTAMP
        WHERE Queue_ID = ?
    """, (queue_id,))
    conn.commit()
    conn.close()


def mark_failed(queue_id, error):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE send_queue SET Status = 'failed', Error = ?
        WHERE Queue_ID = ?
    """, (str(error)[:500], queue_id))
    conn.commit()
    conn.close()


def send_single_email(queue_item, config):
    """Send one email from the queue."""
    cin = queue_item['CIN']
    strategy = queue_item['Strategy'] or config.get('default_strategy', 'thompson')
    test_email = queue_item['Test_Email'] or config.get('test_email_fallback', '') or None
    forced_variant = queue_item['Variant_Key']

    # Force test mode check
    if config.get('force_test_mode', 'false') == 'true' and not test_email:
        test_email = config.get('test_email_fallback', '')
        if not test_email:
            return False, "Test mode on but no test email configured"

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get lead info
    cursor.execute("""
        SELECT q.CIN, q.CompanyName, q.nic_code, q.State, q.PaidupCapital,
            e.Personalized_Sentence, e.Competitor_Count, e.Has_GMB, e.Website_URL,
            cc.Email_Address, cc.Full_Name
        FROM vw_qualified_leads q
        JOIN company_enrichment e ON q.CIN = e.CIN
        JOIN company_contacts cc ON q.CIN = cc.CIN AND cc.Is_Primary_Contact = 1
        WHERE q.CIN = ?
    """, (cin,))
    lead = cursor.fetchone()

    if not lead:
        conn.close()
        return False, f"Lead {cin} not found or no primary contact"

    lead = dict(lead)
    recipient = test_email or lead['Email_Address']

    if not recipient:
        conn.close()
        return False, f"No email address for {cin}"

    # Determine variant
    if forced_variant:
        variant_key = forced_variant
    else:
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from api.campaign_engine import get_campaign_variant, get_ab_variant

            lead_info = {
                'nic_code': lead['nic_code'],
                'Competitor_Count': lead['Competitor_Count'],
                'Has_GMB': lead['Has_GMB']
            }
            variant_base = get_campaign_variant(lead_info)

            if strategy == 'thompson':
                try:
                    from bayesian_engine import select_variant_thompson
                    variant_key = select_variant_thompson(variant_base, cin)
                except ImportError:
                    variant_key = get_ab_variant(cin, variant_base)
            elif strategy == 'even_split':
                variant_key = get_ab_variant(cin, variant_base)
            else:
                variant_key = get_ab_variant(cin, variant_base)
        except ImportError:
            variant_key = 'generic_audit_v1_a'

    # Get template
    cursor.execute(
        "SELECT * FROM campaign_templates WHERE Variant_Key = ? AND Is_Active = 1",
        (variant_key,)
    )
    tmpl = cursor.fetchone()

    if not tmpl:
        conn.close()
        return False, f"Template {variant_key} not found or inactive"

    tmpl = dict(tmpl)

    # Build email
    now = datetime.now()
    batch_id = f"batch_{date.today().isoformat().replace('-', '_')}"
    company_name = lead['CompanyName'].title() if lead['CompanyName'] else 'Your Company'
    sentence = lead['Personalized_Sentence'] or ''

    audit_url = f"{tmpl['CTA_URL']}?utm_source=coldemail&utm_medium=outreach&utm_campaign={batch_id}&cin={cin}"

    # We'll insert analytics row first to get the ID for tracking
    cursor.execute("""
        INSERT INTO outreach_analytics
        (CIN, Email_Sent_Date, Batch_ID, Campaign_Variant, Subject_Line,
         NIC_Code, State, PaidupCapital, Competitor_Count, Has_GMB,
         Send_Hour, Send_DayOfWeek)
        VALUES (?, date('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (cin, batch_id, variant_key, tmpl['Subject_Line'],
          lead['nic_code'], lead['State'], lead['PaidupCapital'],
          lead['Competitor_Count'], lead['Has_GMB'],
          now.hour, now.weekday()))
    conn.commit()
    analytics_id = cursor.lastrowid

    # Build tracking URLs
    tracking_pixel_url = f"https://clickcatalyst.digital/api/track/email-open?aid={analytics_id}&cin={cin}"
    click_url = f"https://clickcatalyst.digital/api/track/email-click?aid={analytics_id}&cin={cin}&url={audit_url}"
    unsubscribe_url = f"https://clickcatalyst.digital/api/unsubscribe?cin={cin}"

    variables = {
        'company_name': company_name,
        'personalized_sentence': sentence,
        'audit_url': click_url,
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

    # Send via SMTP
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    sender_email = os.getenv('SENDER_EMAIL', 'pujan@clickcatalyst.digital')
    sender_pass = os.getenv('SENDER_APP_PASS', '')
    sender_name = 'Pujan from ClickCatalyst'

    msg = MIMEMultipart('alternative')
    msg['From'] = f"{sender_name} <{sender_email}>"
    msg['To'] = recipient
    msg['Subject'] = subject
    msg['Reply-To'] = sender_email

    # Add unsubscribe header
    msg['List-Unsubscribe'] = f"<{unsubscribe_url}>"
    msg['List-Unsubscribe-Post'] = "List-Unsubscribe=One-Click"

    msg.attach(MIMEText(plain, 'plain'))
    msg.attach(MIMEText(html, 'html'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_pass)
            server.send_message(msg)

        # Update pipeline status
        cursor.execute("""
            UPDATE company_enrichment
            SET Pipeline_Status = 'Outreach_Sent', Email_Sent_Date = date('now')
            WHERE CIN = ? AND Pipeline_Status != 'Outreach_Sent'
        """, (cin,))
        conn.commit()
        conn.close()

        print(f"   ✅ Sent to {recipient} ({company_name}) [{variant_key}]")
        return True, None

    except Exception as e:
        error_msg = str(e).lower()

        # Classify bounce
        hard_signals = ['user unknown', 'mailbox not found', 'recipient rejected',
                       'no such user', 'does not exist', 'invalid recipient',
                       '550', '551', '552', '553', '554']
        is_hard = any(s in error_msg for s in hard_signals)

        cursor.execute("""
            UPDATE outreach_analytics SET Bounced = 1, Send_Error = ?
            WHERE Analytics_ID = ?
        """, (str(e)[:200], analytics_id))

        if is_hard:
            cursor.execute("""
                UPDATE company_contacts SET Email_Label = 'Bounced'
                WHERE CIN = ? AND Is_Primary_Contact = 1
            """, (cin,))
            cursor.execute("""
                UPDATE company_enrichment
                SET Pipeline_Status = 'Hard_Bounce', Last_Error = ?
                WHERE CIN = ?
            """, (f"Hard bounce: {str(e)[:150]}", cin))
            print(f"   ⛔ HARD BOUNCE: {recipient} — {e}")
        else:
            cursor.execute("""
                UPDATE company_enrichment SET Last_Error = ?
                WHERE CIN = ?
            """, (f"Soft bounce: {str(e)[:150]}", cin))
            print(f"   ⚠ SOFT BOUNCE: {recipient} — {e}")

        conn.commit()
        conn.close()
        return False, str(e)


def process_queue():
    """Main queue processing loop — called each cycle."""
    config = get_config()

    # Check if auto-send is enabled
    if config.get('auto_send_enabled', 'true') != 'true':
        print("   ⏸ Auto-send is paused")
        return 0

    # Check send window
    in_window, reason = is_send_window(config)
    if not in_window:
        print(f"   ⏸ {reason}")
        return 0

    # Check warmup limit
    daily_limit, warmup_day = get_warmup_limit()
    sent_today = get_sent_today()
    remaining = max(0, daily_limit - sent_today)

    if remaining == 0:
        print(f"   ✅ Daily limit reached ({daily_limit})")
        return 0

    # Check Bayesian volume adjustment
    try:
        from bayesian_engine import get_volume_adjustment, should_send_today
        ok, del_reason, score = should_send_today()
        if not ok:
            print(f"   ⚠ Deliverability: {del_reason} (score: {score:.3f})")
            return 0
        adjustment = get_volume_adjustment()
        if adjustment < 1.0:
            remaining = max(1, int(remaining * adjustment))
            print(f"   ⚡ Volume adjusted: {remaining} (reputation: {score:.3f})")
    except ImportError:
        pass

    # How many to send this cycle
    # During peak hours, send more per cycle. Off-peak, spread them out.
    interval = int(config.get('send_interval_minutes', '15'))
    if is_peak_hour(config):
        per_cycle = max(1, remaining // 2)  # Send half the remaining during peak
    else:
        cycles_left = max(1, (int(config.get('end_hour', '17')) - datetime.now().hour) * (60 // interval))
        per_cycle = max(1, remaining // cycles_left)

    # Get queued emails
    queued = get_queued_emails(per_cycle)
    if not queued:
        print(f"   ○ No emails in queue (remaining capacity: {remaining})")
        return 0

    print(f"   📬 Processing {len(queued)} emails (day {warmup_day}, limit {daily_limit}, sent {sent_today})")

    sent = 0
    for item in queued:
        mark_sending(item['Queue_ID'])
        success, error = send_single_email(item, config)
        if success:
            mark_sent(item['Queue_ID'])
            sent += 1
        else:
            mark_failed(item['Queue_ID'], error)

        # Small delay between sends (2-5 seconds, randomized)
        import random
        time.sleep(random.uniform(2, 5))

    print(f"   Sent {sent}/{len(queued)} emails")
    return sent


# ---------------------------------------------------------------------------
# STATUS
# ---------------------------------------------------------------------------

def show_status():
    """Show current queue and system status."""
    config = get_config()
    daily_limit, warmup_day = get_warmup_limit()
    sent_today = get_sent_today()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT Status, COUNT(*) FROM send_queue
        GROUP BY Status
    """)
    status_counts = {row[0]: row[1] for row in cursor.fetchall()}

    cursor.execute("""
        SELECT sq.Queue_ID, sq.CIN, sq.Variant_Key, sq.Strategy,
               sq.Status, sq.Scheduled_At, sq.Test_Email,
               q.CompanyName
        FROM send_queue sq
        LEFT JOIN vw_qualified_leads q ON sq.CIN = q.CIN
        WHERE sq.Status = 'queued'
        ORDER BY sq.Scheduled_At ASC
        LIMIT 10
    """)
    upcoming = cursor.fetchall()
    conn.close()

    in_window, window_reason = is_send_window(config)

    print("📬 QUEUE STATUS")
    print(f"   Warmup day:   {warmup_day}")
    print(f"   Daily limit:  {daily_limit}")
    print(f"   Sent today:   {sent_today}")
    print(f"   Remaining:    {max(0, daily_limit - sent_today)}")
    print(f"   Auto-send:    {'ON' if config.get('auto_send_enabled', 'true') == 'true' else 'PAUSED'}")
    print(f"   Send window:  {'✅ ' + window_reason if in_window else '⏸ ' + window_reason}")
    print(f"   Strategy:     {config.get('default_strategy', 'thompson')}")
    print(f"   Interval:     every {config.get('send_interval_minutes', '15')} min")
    print()
    print(f"   Queue:  queued={status_counts.get('queued', 0)}  "
          f"sending={status_counts.get('sending', 0)}  "
          f"sent={status_counts.get('sent', 0)}  "
          f"failed={status_counts.get('failed', 0)}")
    print()

    if upcoming:
        print("   Next up:")
        for row in upcoming:
            qid, cin, variant, strategy, status, sched, test, company = row
            name = (company or cin)[:25]
            v = variant or 'auto'
            t = f" → {test}" if test else ""
            print(f"      #{qid} {name:<26} {v:<30} {strategy}{t}")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Email queue worker')
    parser.add_argument('--daemon', action='store_true', help='Run continuously')
    parser.add_argument('--status', action='store_true', help='Show queue status')
    parser.add_argument('--once', action='store_true', help='Process queue once then exit')
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    print("📬 Queue Worker")
    print(f"   DB: {DB_PATH}")
    print()

    if args.daemon:
        print("   Running in daemon mode...")
        print()
        while True:
            try:
                config = get_config()
                interval = int(config.get('send_interval_minutes', '15')) * 60
                now = datetime.now().strftime('%H:%M:%S')
                print(f"[{now}] Checking queue...")
                process_queue()
                print()
                time.sleep(interval)
            except KeyboardInterrupt:
                print("\n   Stopped.")
                break
            except Exception as e:
                print(f"   ❌ Error: {e}")
                time.sleep(60)
    else:
        process_queue()


if __name__ == '__main__':
    main()