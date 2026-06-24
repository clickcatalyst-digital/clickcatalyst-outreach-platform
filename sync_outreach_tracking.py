#!/usr/bin/env python3
"""
sync_outreach_tracking.py

Pulls unsynced outreach tracking events from Firestore and updates local SQLite.
Run manually or via cron on your local Mac.

Usage:
    python sync_outreach_tracking.py              # sync all unsynced events
    python sync_outreach_tracking.py --dry-run    # preview without writing to SQLite
    python sync_outreach_tracking.py --daemon     # run continuously every 5 minutes

Requirements:
    pip install firebase-admin --break-system-packages

Setup:
    Set GOOGLE_APPLICATION_CREDENTIALS env var to your Firebase service account key path,
    or set FIREBASE_CREDENTIALS_PATH.
"""

import sqlite3
import os
import sys
import time
import argparse
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()  # load .env (DB_PATH, FIREBASE creds path, etc.)
import db_factory  # routes the main DB to Turso when TURSO_* env vars are set

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

DB_PATH = os.getenv(
    'DB_PATH',
    '/Users/pujan/Developer/data_collector/indian_companies/company_master_data.db'
)

FIRESTORE_COLLECTION = 'outreach_tracking'
BATCH_SIZE = 100
DAEMON_INTERVAL = 300  # 5 minutes

# ---------------------------------------------------------------------------
# FIREBASE INIT
# ---------------------------------------------------------------------------

def init_firebase():
    """Initialize Firebase Admin SDK."""
    import firebase_admin
    from firebase_admin import credentials, firestore   # firestore submodule must be imported explicitly

    if firebase_admin._apps:
        return firestore.client()

    cred_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS') or os.getenv('FIREBASE_CREDENTIALS_PATH')
    if not cred_path:
        print("❌ No Firebase credentials found.")
        print("   Set GOOGLE_APPLICATION_CREDENTIALS or FIREBASE_CREDENTIALS_PATH env var.")
        sys.exit(1)

    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)
    return firestore.client()


# ---------------------------------------------------------------------------
# EVENT HANDLERS
# ---------------------------------------------------------------------------

def handle_open(cursor, event):
    """Mark email as opened in outreach_analytics."""
    aid = event.get('aid')
    if not aid:
        return False

    cursor.execute("""
        UPDATE outreach_analytics
        SET Email_Opened = 1, Opened_At = ?
        WHERE Analytics_ID = ? AND (Email_Opened IS NULL OR Email_Opened = 0)
    """, (event['timestamp_iso'], aid))
    return cursor.rowcount > 0


def handle_click(cursor, event):
    """Mark audit link as clicked in outreach_analytics."""
    aid = event.get('aid')
    if not aid:
        return False

    cursor.execute("""
        UPDATE outreach_analytics
        SET Audit_Link_Clicked = 1, Clicked_At = ?
        WHERE Analytics_ID = ? AND (Audit_Link_Clicked IS NULL OR Audit_Link_Clicked = 0)
    """, (event['timestamp_iso'], aid))
    return cursor.rowcount > 0


def handle_unsubscribe(cursor, event):
    """Mark lead as unsubscribed in company_enrichment."""
    cin = event.get('cin')
    if not cin:
        return False

    cursor.execute("""
        UPDATE company_enrichment
        SET Unsubscribed = 1, Unsubscribed_Date = ?, Pipeline_Status = 'Unsubscribed'
        WHERE CIN = ? AND (Unsubscribed IS NULL OR Unsubscribed = 0)
    """, (event['timestamp_iso'][:10], cin))
    return cursor.rowcount > 0


def handle_conversion(cursor, event):
    """Mark lead as converted in outreach_analytics."""
    cin = event.get('cin')
    conversion_type = event.get('conversion_type', 'unknown')
    if not cin:
        return False

    cursor.execute("""
        UPDATE outreach_analytics
        SET Converted = 1, Converted_At = ?, Conversion_Type = ?
        WHERE CIN = ? AND (Converted IS NULL OR Converted = 0)
    """, (event['timestamp_iso'], conversion_type, cin))
    return cursor.rowcount > 0


HANDLERS = {
    'open': handle_open,
    'click': handle_click,
    'unsubscribe': handle_unsubscribe,
    'conversion': handle_conversion,
}


# ---------------------------------------------------------------------------
# SYNC LOGIC
# ---------------------------------------------------------------------------

def sync_events(db, dry_run=False):
    """Pull unsynced events from Firestore and process them."""
    from google.cloud.firestore_v1.base_query import FieldFilter

    # NOTE: no .order_by('timestamp') — combining it with the synced filter would need a
    # Firestore composite index. Events are independent idempotent updates, so order is irrelevant.
    docs = (
        db.collection(FIRESTORE_COLLECTION)
        .where(filter=FieldFilter('synced', '==', False))
        .limit(BATCH_SIZE)
        .get()
    )

    if not docs:
        print("   No unsynced events found.")
        return 0

    conn = db_factory.connect(DB_PATH)
    cursor = conn.cursor()

    processed = 0
    skipped = 0
    errors = 0

    for doc in docs:
        data = doc.to_dict()
        event_type = data.get('type')
        handler = HANDLERS.get(event_type)

        # Convert Firestore timestamp to ISO string
        ts = data.get('timestamp')
        if ts:
            data['timestamp_iso'] = ts.isoformat() if hasattr(ts, 'isoformat') else str(ts)
        else:
            data['timestamp_iso'] = datetime.utcnow().isoformat()

        if not handler:
            print(f"   ⚠ Unknown event type: {event_type} (doc {doc.id})")
            skipped += 1
            continue

        if dry_run:
            print(f"   [DRY RUN] Would process: {event_type} | aid={data.get('aid')} | cin={data.get('cin')}")
            processed += 1
            continue

        try:
            success = handler(cursor, data)
            if success:
                print(f"   ✅ {event_type} | aid={data.get('aid')} | cin={data.get('cin')}")
                processed += 1
            else:
                print(f"   ○ {event_type} | aid={data.get('aid')} | cin={data.get('cin')} — no matching row updated")
                skipped += 1

            # Mark as synced in Firestore regardless (to prevent re-processing)
            doc.reference.update({'synced': True, 'synced_at': datetime.utcnow().isoformat()})

        except Exception as e:
            print(f"   ❌ Error processing {event_type} (doc {doc.id}): {e}")
            errors += 1

    if not dry_run:
        conn.commit()
    conn.close()

    print(f"   Processed: {processed} | Skipped: {skipped} | Errors: {errors}")
    return processed


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def write_heartbeat(processed=0):
    """Record that the sync ran, so the orchestrator can alert if it stalls."""
    try:
        conn = db_factory.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tracking_sync_heartbeat (
                ID INTEGER PRIMARY KEY CHECK (ID = 1),
                Last_Sync_At TEXT,
                Events_Last INTEGER
            )
        """)
        conn.execute("""
            INSERT INTO tracking_sync_heartbeat (ID, Last_Sync_At, Events_Last)
            VALUES (1, ?, ?)
            ON CONFLICT(ID) DO UPDATE SET
                Last_Sync_At = excluded.Last_Sync_At,
                Events_Last  = excluded.Events_Last
        """, (datetime.utcnow().isoformat(), processed or 0))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"   ⚠ heartbeat write failed: {e}")


def main():
    parser = argparse.ArgumentParser(description='Sync outreach tracking from Firestore to SQLite')
    parser.add_argument('--dry-run', action='store_true', help='Preview without writing to SQLite')
    parser.add_argument('--daemon', action='store_true', help='Run continuously every 5 minutes')
    args = parser.parse_args()

    print("🔄 Outreach Tracking Sync")
    print(f"   DB: {DB_PATH}")
    print(f"   Collection: {FIRESTORE_COLLECTION}")
    print()

    db = init_firebase()

    if args.daemon:
        print(f"   Running in daemon mode (every {DAEMON_INTERVAL}s)...")
        print()
        while True:
            try:
                now = datetime.now().strftime('%H:%M:%S')
                print(f"[{now}] Checking for new events...")
                n = sync_events(db, dry_run=args.dry_run)
                if not args.dry_run:
                    write_heartbeat(n)
                print()
            except KeyboardInterrupt:
                print("\n   Stopped by user.")
                break
            except Exception as e:
                print(f"   ❌ Sync error: {e}")
            time.sleep(DAEMON_INTERVAL)
    else:
        n = sync_events(db, dry_run=args.dry_run)
        if not args.dry_run:
            write_heartbeat(n)


if __name__ == '__main__':
    main()