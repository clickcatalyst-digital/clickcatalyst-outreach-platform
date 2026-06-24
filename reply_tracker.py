#!/usr/bin/env python3
"""
reply_tracker.py

Checks Gmail inbox for replies to outreach emails and updates outreach_analytics.
Uses Gmail API to search for replies matching our sent subject lines.

Usage:
    python reply_tracker.py              # check once
    python reply_tracker.py --daemon     # check every 10 minutes

Setup:
    1. Enable Gmail API in Google Cloud Console
    2. Download OAuth2 credentials as credentials.json
    3. First run will open browser for auth, saves token.json
    4. pip install google-auth-oauthlib google-api-python-client --break-system-packages
"""

import sqlite3
import os
import sys
import time
import argparse
import json
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()  # load .env (SENDER_EMAIL, DB_PATH, etc.)

DB_PATH = os.getenv(
    'DB_PATH',
    '/Users/pujan/Developer/data_collector/indian_companies/company_master_data.db'
)

CREDENTIALS_FILE = os.getenv('GMAIL_CREDENTIALS', 'credentials.json')
TOKEN_FILE = os.getenv('GMAIL_TOKEN', 'token.json')
SENDER_EMAIL = os.getenv('SENDER_EMAIL', 'pujan@clickcatalyst.digital')
DAEMON_INTERVAL = 600  # 10 minutes

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']


# ---------------------------------------------------------------------------
# GMAIL AUTH
# ---------------------------------------------------------------------------

def get_gmail_service():
    """Authenticate and return Gmail API service."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                print(f"❌ {CREDENTIALS_FILE} not found.")
                print("   Download OAuth2 credentials from Google Cloud Console.")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, 'w') as f:
            f.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)


# ---------------------------------------------------------------------------
# REPLY DETECTION
# ---------------------------------------------------------------------------

def get_unreplied_outreach(conn):
    """Get outreach records that haven't been marked as replied."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            oa.Analytics_ID,
            oa.CIN,
            oa.Subject_Line,
            oa.Email_Sent_Date,
            cc.Email_Address
        FROM outreach_analytics oa
        JOIN company_contacts cc ON oa.CIN = cc.CIN AND cc.Is_Primary_Contact = 1
        WHERE (oa.Reply_Received IS NULL OR oa.Reply_Received = 0)
          AND oa.Email_Sent_Date >= date('now', '-30 days')
        ORDER BY oa.Email_Sent_Date DESC
    """)
    return cursor.fetchall()


def check_for_replies(service, outreach_records):
    """Check Gmail for replies to each outreach email."""
    replies_found = []

    for record in outreach_records:
        analytics_id, cin, subject, sent_date, recipient_email = record

        if not recipient_email or not subject:
            continue

        # Search for replies from this recipient
        query = f'from:{recipient_email} subject:"{subject}" after:{sent_date}'

        try:
            results = service.users().messages().list(
                userId='me',
                q=query,
                maxResults=5
            ).execute()

            messages = results.get('messages', [])

            if messages:
                # Get the first reply's timestamp
                msg = service.users().messages().get(
                    userId='me',
                    id=messages[0]['id'],
                    format='metadata',
                    metadataHeaders=['Date', 'From', 'Subject']
                ).execute()

                # Extract date from headers
                headers = {h['name']: h['value'] for h in msg.get('payload', {}).get('headers', [])}
                reply_date = headers.get('Date', '')

                # Check if the reply is from the recipient (not from us)
                from_header = headers.get('From', '')
                if SENDER_EMAIL.lower() not in from_header.lower():
                    replies_found.append({
                        'analytics_id': analytics_id,
                        'cin': cin,
                        'recipient': recipient_email,
                        'subject': subject,
                        'reply_date': reply_date,
                        'gmail_message_id': messages[0]['id'],
                    })

        except Exception as e:
            print(f"   ⚠ Gmail API error for {recipient_email}: {e}")
            continue

    return replies_found


def update_replies_in_db(conn, replies):
    """Mark outreach records as replied in SQLite."""
    cursor = conn.cursor()

    for reply in replies:
        cursor.execute("""
            UPDATE outreach_analytics
            SET Reply_Received = 1,
                Reply_Date = CURRENT_TIMESTAMP
            WHERE Analytics_ID = ?
        """, (reply['analytics_id'],))

        print(f"   ✅ Reply detected: {reply['recipient']} → {reply['subject'][:50]}...")

    conn.commit()

    # Auto-summarize each newly-replied thread (best-effort; needs OPENROUTER_API_KEY).
    for reply in replies:
        try:
            from us_lead_engine.summarizer import summarize_contact
            summarize_contact(reply['cin'])
        except Exception as e:
            print(f"   [summary] failed for {reply['cin']}: {e}")

    return len(replies)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def check_replies():
    """Run one cycle of reply checking."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    records = get_unreplied_outreach(conn)
    print(f"   Checking {len(records)} unreplied outreach emails...")

    if not records:
        print("   No unreplied outreach to check.")
        conn.close()
        return 0

    service = get_gmail_service()
    replies = check_for_replies(service, records)

    if replies:
        count = update_replies_in_db(conn, replies)
        print(f"   Found {count} new replies!")
    else:
        print("   No new replies found.")

    conn.close()
    return len(replies)


def main():
    parser = argparse.ArgumentParser(description='Track replies to outreach emails via Gmail API')
    parser.add_argument('--daemon', action='store_true', help='Run continuously')
    args = parser.parse_args()

    print("📬 Reply Tracker")
    print(f"   DB: {DB_PATH}")
    print(f"   Sender: {SENDER_EMAIL}")
    print()

    if args.daemon:
        print(f"   Running in daemon mode (every {DAEMON_INTERVAL}s)...\n")
        while True:
            try:
                now = datetime.now().strftime('%H:%M:%S')
                print(f"[{now}] Checking for replies...")
                check_replies()
                print()
            except KeyboardInterrupt:
                print("\n   Stopped.")
                break
            except Exception as e:
                print(f"   ❌ Error: {e}")
            time.sleep(DAEMON_INTERVAL)
    else:
        check_replies()


if __name__ == '__main__':
    main()