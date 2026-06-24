#!/usr/bin/env python3
"""
send_scheduler.py

Smart email scheduling system for the outreach pipeline.
Determines WHEN to send emails based on:
  - Day of week (avoids weekends)
  - Time of day (optimizes for business hours in recipient's timezone)
  - Daily volume limits (warmup-aware)
  - Per-lead optimal timing (learns from historical data)

Usage:
    python send_scheduler.py                    # show today's schedule
    python send_scheduler.py --execute          # actually send the scheduled batch
    python send_scheduler.py --plan-week        # show full week plan

This wraps email_engine_04.py — it decides WHO gets emailed WHEN,
then calls the email engine to actually send.
"""

import sqlite3
import os
import sys
import json
from datetime import datetime, timedelta, date
from collections import defaultdict

DB_PATH = os.getenv(
    'DB_PATH',
    '/Users/pujan/Developer/data_collector/indian_companies/company_master_data.db'
)


# ---------------------------------------------------------------------------
# WARMUP SCHEDULE — daily volume limits
# ---------------------------------------------------------------------------

def get_warmup_day():
    """Calculate which day of warmup we're on based on first send date."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT MIN(Email_Sent_Date) FROM outreach_analytics")
    first_send = cursor.fetchone()[0]
    conn.close()

    if not first_send:
        return 0  # Haven't started yet

    first_date = datetime.strptime(first_send, '%Y-%m-%d').date()
    return (date.today() - first_date).days


def get_daily_limit():
    """Returns how many emails we should send today based on warmup phase."""
    day = get_warmup_day()

    # Warmup schedule — conservative ramp
    schedule = {
        (0, 3):   5,     # Days 0-3:   5/day
        (4, 7):   10,    # Days 4-7:   10/day
        (8, 14):  20,    # Week 2:     20/day
        (15, 21): 35,    # Week 3:     35/day
        (22, 30): 50,    # Week 4:     50/day
        (31, 60): 75,    # Month 2:    75/day
        (61, 999): 100,  # Month 3+:   100/day
    }

    for (start, end), limit in schedule.items():
        if start <= day <= end:
            return limit

    return 5  # Safe default


def get_sent_today():
    """How many emails were sent today already."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM outreach_analytics
        WHERE Email_Sent_Date = date('now')
    """)
    count = cursor.fetchone()[0]
    conn.close()
    return count


# ---------------------------------------------------------------------------
# OPTIMAL SEND WINDOWS
# ---------------------------------------------------------------------------

# IST business hours mapped to common recipient timezones
# Indian companies = IST, so 9:30 AM - 6:30 PM IST
SEND_WINDOWS = {
    'IN': {  # India Standard Time
        'start_hour': 9,
        'end_hour': 17,
        'peak_hours': [10, 11, 14, 15],  # 10-11 AM, 2-3 PM IST
        'avoid_hours': [13],              # Lunch hour
    },
}

DEFAULT_TIMEZONE = 'IN'


def is_good_send_time(hour=None, day_of_week=None):
    """Check if now is a good time to send."""
    now = datetime.now()
    h = hour or now.hour
    dow = day_of_week or now.weekday()

    # Never send on weekends
    if dow >= 5:
        return False, "Weekend — no sends"

    tz = SEND_WINDOWS[DEFAULT_TIMEZONE]

    if h < tz['start_hour']:
        return False, f"Too early — wait until {tz['start_hour']}:00"
    if h >= tz['end_hour']:
        return False, f"Too late — business hours ended at {tz['end_hour']}:00"
    if h in tz.get('avoid_hours', []):
        return False, f"Lunch hour ({h}:00) — better to wait"

    is_peak = h in tz.get('peak_hours', [])
    return True, f"{'Peak hour' if is_peak else 'Good time'} — {h}:00"


def get_next_good_window():
    """Find the next good send window."""
    now = datetime.now()

    for delta_days in range(7):
        check_date = now + timedelta(days=delta_days)
        dow = check_date.weekday()

        if dow >= 5:  # Skip weekends
            continue

        tz = SEND_WINDOWS[DEFAULT_TIMEZONE]

        for h in tz.get('peak_hours', []):
            check_time = check_date.replace(hour=h, minute=0, second=0)
            if check_time > now:
                return check_time

        # If no peak hours left today, try start of next business day
        if delta_days > 0:
            return check_date.replace(hour=tz['start_hour'], minute=30, second=0)

    return now + timedelta(days=1)


# ---------------------------------------------------------------------------
# A/B TEST: TIME-OF-DAY AND DAY-OF-WEEK
# ---------------------------------------------------------------------------

def get_time_performance():
    """Analyze historical performance by send hour and day of week."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # By hour
    cursor.execute("""
        SELECT
            Send_Hour,
            COUNT(*) as sent,
            SUM(CASE WHEN Email_Opened = 1 THEN 1 ELSE 0 END) as opened,
            SUM(CASE WHEN Audit_Link_Clicked = 1 THEN 1 ELSE 0 END) as clicked,
            SUM(CASE WHEN Reply_Received = 1 THEN 1 ELSE 0 END) as replied,
            SUM(CASE WHEN Converted = 1 THEN 1 ELSE 0 END) as converted
        FROM outreach_analytics
        WHERE Send_Hour IS NOT NULL
        GROUP BY Send_Hour
        ORDER BY Send_Hour
    """)
    by_hour = [dict(zip(['hour', 'sent', 'opened', 'clicked', 'replied', 'converted'], row))
               for row in cursor.fetchall()]

    # By day of week
    cursor.execute("""
        SELECT
            Send_DayOfWeek,
            COUNT(*) as sent,
            SUM(CASE WHEN Email_Opened = 1 THEN 1 ELSE 0 END) as opened,
            SUM(CASE WHEN Audit_Link_Clicked = 1 THEN 1 ELSE 0 END) as clicked,
            SUM(CASE WHEN Reply_Received = 1 THEN 1 ELSE 0 END) as replied,
            SUM(CASE WHEN Converted = 1 THEN 1 ELSE 0 END) as converted
        FROM outreach_analytics
        WHERE Send_DayOfWeek IS NOT NULL
        GROUP BY Send_DayOfWeek
        ORDER BY Send_DayOfWeek
    """)
    day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    by_day = []
    for row in cursor.fetchall():
        d = dict(zip(['day_num', 'sent', 'opened', 'clicked', 'replied', 'converted'], row))
        d['day_name'] = day_names[d['day_num']] if d['day_num'] < 7 else '?'
        by_day.append(d)

    conn.close()
    return by_hour, by_day


# ---------------------------------------------------------------------------
# QUEUE BUILDER — who to send to today
# ---------------------------------------------------------------------------

def get_todays_queue(limit):
    """Build the send queue for today, prioritized by lead quality."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            q.CIN,
            q.CompanyName,
            q.State,
            q.PaidupCapital,
            q.nic_code,
            e.Pipeline_Status,
            e.Competitor_Count,
            e.Personalized_Sentence,
            e.Website_URL,
            cc.Email_Address,
            cc.Full_Name
        FROM vw_qualified_leads q
        JOIN company_enrichment e ON q.CIN = e.CIN
        JOIN company_contacts cc ON q.CIN = cc.CIN AND cc.Is_Primary_Contact = 1
        WHERE e.Pipeline_Status = 'Intelligence_Ready'
          AND (e.Unsubscribed IS NULL OR e.Unsubscribed = 0)
          AND cc.Email_Address IS NOT NULL
        ORDER BY q.PaidupCapital DESC
        LIMIT ?
    """, (limit,))

    columns = [desc[0] for desc in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# DISPLAY
# ---------------------------------------------------------------------------

def show_schedule():
    """Display today's send plan."""
    now = datetime.now()
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    print("📅 SEND SCHEDULE")
    print(f"   Date: {now.strftime('%d %b %Y')} ({day_names[now.weekday()]})")
    print(f"   Time: {now.strftime('%H:%M')} IST")
    print()

    # Warmup status
    warmup_day = get_warmup_day()
    daily_limit = get_daily_limit()
    sent_today = get_sent_today()
    remaining = max(0, daily_limit - sent_today)

    print(f"   Warmup day:   {warmup_day}")
    print(f"   Daily limit:  {daily_limit}")
    print(f"   Sent today:   {sent_today}")
    print(f"   Remaining:    {remaining}")
    print()

    # Current window
    good, reason = is_good_send_time()
    print(f"   Send now?     {'✅ Yes' if good else '❌ No'} — {reason}")

    if not good:
        next_window = get_next_good_window()
        print(f"   Next window:  {next_window.strftime('%a %d %b, %H:%M')}")
    print()

    # Queue preview
    if remaining > 0:
        queue = get_todays_queue(remaining)
        print(f"   📋 Queue ({len(queue)} leads ready):")
        print(f"   {'CIN':<22} {'Company':<30} {'Contact':<25} {'Capital'}")
        print(f"   {'─'*22} {'─'*30} {'─'*25} {'─'*12}")
        for lead in queue[:15]:
            cap = f"₹{float(lead['PaidupCapital'])/100000:.1f}L" if lead['PaidupCapital'] else '—'
            print(f"   {lead['CIN']:<22} {lead['CompanyName'][:28]:<30} {lead['Email_Address'][:23]:<25} {cap}")
        if len(queue) > 15:
            print(f"   ... and {len(queue) - 15} more")
    else:
        print("   ✅ Daily limit reached. No more sends today.")

    print()

    # Time performance (if data exists)
    by_hour, by_day = get_time_performance()
    if by_hour:
        print("   📊 Historical Performance by Hour:")
        for h in by_hour:
            open_rate = f"{h['opened']/h['sent']*100:.0f}%" if h['sent'] > 0 else '—'
            click_rate = f"{h['clicked']/h['sent']*100:.0f}%" if h['sent'] > 0 else '—'
            print(f"      {h['hour']:02d}:00  sent={h['sent']:>3}  open={open_rate:>4}  click={click_rate:>4}")
        print()

    if by_day:
        print("   📊 Historical Performance by Day:")
        for d in by_day:
            open_rate = f"{d['opened']/d['sent']*100:.0f}%" if d['sent'] > 0 else '—'
            click_rate = f"{d['clicked']/d['sent']*100:.0f}%" if d['sent'] > 0 else '—'
            print(f"      {d['day_name']}  sent={d['sent']:>3}  open={open_rate:>4}  click={click_rate:>4}")
        print()


def show_week_plan():
    """Show projected send plan for the week."""
    daily_limit = get_daily_limit()
    now = datetime.now()
    day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

    print("📅 WEEK PLAN")
    print(f"   Daily limit: {daily_limit} (warmup day {get_warmup_day()})")
    print()

    total = 0
    for i in range(7):
        d = now + timedelta(days=i)
        dow = d.weekday()
        day_name = day_names[dow]

        if dow >= 5:
            print(f"   {d.strftime('%d %b')} ({day_name})  — weekend, no sends")
        else:
            is_today = i == 0
            sent = get_sent_today() if is_today else 0
            remaining = daily_limit - sent
            total += remaining if remaining > 0 else daily_limit
            marker = " ← today" if is_today else ""
            print(f"   {d.strftime('%d %b')} ({day_name})  {daily_limit} emails{marker}")

    print(f"\n   Total this week: ~{total} emails")


# ---------------------------------------------------------------------------
# EXECUTE — actually trigger sends
# ---------------------------------------------------------------------------

def execute_scheduled_batch():
    """Send today's batch respecting warmup limits and send windows."""
    good, reason = is_good_send_time()
    if not good:
        print(f"   ❌ Not a good send time: {reason}")
        next_window = get_next_good_window()
        print(f"   Next window: {next_window.strftime('%a %d %b, %H:%M')}")
        return

    daily_limit = get_daily_limit()
    sent_today = get_sent_today()
    remaining = max(0, daily_limit - sent_today)

    if remaining == 0:
        print("   ✅ Daily limit reached. No more sends today.")
        return

    # Check deliverability and adjust volume
    try:
        from bayesian_engine import should_send_today, get_volume_adjustment
        ok, del_reason, score = should_send_today()
        if not ok:
            print(f"   ⚠ Deliverability check: {del_reason} (score: {score:.3f})")
            print(f"   Skipping sends until reputation recovers.")
            return
        adjustment = get_volume_adjustment()
        if adjustment < 1.0:
            remaining = int(remaining * adjustment)
            print(f"   ⚡ Volume adjusted to {remaining} (multiplier: {adjustment:.1f}x, reputation: {score:.3f})")
    except ImportError:
        pass

    print(f"   Sending {remaining} emails (limit: {daily_limit}, already sent: {sent_today})...")
    print()

    try:
        from email_engine_04 import run_email_batch
        run_email_batch(batch_size=remaining)
    except ImportError:
        print("   ❌ Could not import email_engine_04.")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Smart email send scheduler')
    parser.add_argument('--execute', action='store_true', help='Execute scheduled sends')
    parser.add_argument('--plan-week', action='store_true', help='Show week plan')
    parser.add_argument('--time-stats', action='store_true', help='Show time/day performance')
    args = parser.parse_args()

    if args.plan_week:
        show_week_plan()
    elif args.execute:
        show_schedule()
        print("─" * 60)
        execute_scheduled_batch()
    elif args.time_stats:
        by_hour, by_day = get_time_performance()
        if not by_hour and not by_day:
            print("No send data yet — send some emails first.")
        else:
            show_schedule()
    else:
        show_schedule()


if __name__ == '__main__':
    main()