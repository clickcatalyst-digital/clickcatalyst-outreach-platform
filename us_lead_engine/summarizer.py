#!/usr/bin/env python3
"""
us_lead_engine/summarizer.py

Summarizes the email thread for a contact who has REPLIED, so you know where the
conversation stands without reading the thread. Reuses the OpenRouter + free Gemma
pattern (cheap, scales) with a strict "don't invent" gate + template fallback.

Flow:  reply detected -> fetch Gmail thread -> Gemma summary -> store on company_contacts.

CLI:
  python -m us_lead_engine.summarizer --cin APOLLO_xxxx     # summarize one contact
  python -m us_lead_engine.summarizer --all-replied         # summarize every replied contact

Env: OPENROUTER_API_KEY (required for LLM; falls back to a template otherwise).
     Gmail OAuth via reply_tracker (credentials.json / token.json).
"""

import os
import sys
import base64
import sqlite3
import argparse
from datetime import datetime

import requests

from .config import MAIN_DB_PATH as DB_PATH

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = os.getenv("OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free")

SYSTEM_PROMPT = """You summarize a cold-outreach email thread between our company (ClickCatalyst, a Google Ads audit tool for agencies) and a prospect (a US marketing agency).

Write a tight summary (2-4 sentences, max 55 words) capturing:
- where the conversation stands (interested / asked a question / objection / wants a call / not interested)
- any specific question, ask, or next step the prospect raised
- what WE last offered or said

Rules:
- State ONLY what is in the thread. Never invent names, numbers, dates, commitments, or sentiment not present.
- No greeting, no "Based on the thread", no filler. Just the substance, like a quick note to yourself.
- Output ONLY the summary prose."""


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------

def ensure_contact_columns(conn):
    """Additive columns on company_contacts for notes + summary. Idempotent."""
    for ddl in (
        "ALTER TABLE company_contacts ADD COLUMN Notes TEXT",
        "ALTER TABLE company_contacts ADD COLUMN Conversation_Summary TEXT",
        "ALTER TABLE company_contacts ADD COLUMN Summary_Updated_At TEXT",
    ):
        try:
            conn.execute(ddl)
        except sqlite3.OperationalError:
            pass


# ---------------------------------------------------------------------------
# LLM (OpenRouter + Gemma)  — never invents; falls back to template
# ---------------------------------------------------------------------------

def summarize_thread(thread_text):
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key or not (thread_text or "").strip():
        return None
    try:
        resp = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://clickcatalyst.digital",
                "X-Title": "ClickCatalyst Outreach Summarizer",
            },
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": thread_text[:8000]},
                ],
                "temperature": 0.2,
                "max_tokens": 160,
            },
            timeout=30,
        )
        resp.raise_for_status()
        text = (resp.json()["choices"][0]["message"]["content"] or "").strip()
        # Light gate: reject empty / runaway output.
        return text if 20 <= len(text) <= 700 else None
    except Exception as e:
        print(f"   [summarizer] LLM failed: {e}")
        return None


def _template_summary(thread_text):
    them = thread_text.count("THEM:")
    us = thread_text.count("US:")
    return f"Replied — {them} message(s) from them, {us} from us. (Set OPENROUTER_API_KEY for an AI summary.)"


# ---------------------------------------------------------------------------
# Gmail thread fetch  (reuses reply_tracker's OAuth service)
# ---------------------------------------------------------------------------

def _extract_body(payload):
    if not payload:
        return ""
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        try:
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", "ignore")
        except Exception:
            return ""
    for part in payload.get("parts", []) or []:
        t = _extract_body(part)
        if t:
            return t
    return ""


def fetch_thread_text(service, recipient_email, sender_email):
    """Concatenate the to/fro of the Gmail thread involving this recipient."""
    q = f"(from:{recipient_email} OR to:{recipient_email})"
    res = service.users().messages().list(userId="me", q=q, maxResults=10).execute()
    msgs = res.get("messages", [])
    if not msgs:
        return ""
    first = service.users().messages().get(userId="me", id=msgs[0]["id"], format="metadata").execute()
    tid = first.get("threadId")
    thread = service.users().threads().get(userId="me", id=tid, format="full").execute()

    lines = []
    for m in thread.get("messages", []):
        headers = {h["name"]: h["value"] for h in m.get("payload", {}).get("headers", [])}
        frm = headers.get("From", "")
        who = "US" if sender_email.lower() in frm.lower() else "THEM"
        body = _extract_body(m.get("payload")).strip()
        if body:
            # Drop quoted reply chains to keep the summary focused.
            body = "\n".join(l for l in body.splitlines() if not l.strip().startswith(">"))[:1500]
            lines.append(f"{who}: {body.strip()}")
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def summarize_contact(cin, db_path=DB_PATH):
    """Fetch the thread for a CIN's primary contact, summarize, store. Returns summary or None."""
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    ensure_contact_columns(conn)
    row = conn.execute(
        "SELECT Email_Address FROM company_contacts WHERE CIN = ? AND Is_Primary_Contact = 1 LIMIT 1",
        (cin,),
    ).fetchone()
    if not row or not row["Email_Address"]:
        conn.close()
        return None
    email = row["Email_Address"]

    try:
        from reply_tracker import get_gmail_service, SENDER_EMAIL
    except ImportError:
        print("   [summarizer] reply_tracker/Gmail not available — skipping thread fetch")
        conn.close()
        return None

    try:
        service = get_gmail_service()
        thread_text = fetch_thread_text(service, email, SENDER_EMAIL)
    except Exception as e:
        print(f"   [summarizer] Gmail fetch failed for {cin}: {e}")
        conn.close()
        return None

    if not thread_text:
        conn.close()
        return None

    summary = summarize_thread(thread_text) or _template_summary(thread_text)
    conn.execute(
        "UPDATE company_contacts SET Conversation_Summary = ?, Summary_Updated_At = ? WHERE CIN = ? AND Is_Primary_Contact = 1",
        (summary, datetime.utcnow().isoformat(), cin),
    )
    conn.commit()
    conn.close()
    print(f"   [summarizer] {cin}: {summary[:80]}…")
    return summary


def summarize_all_replied(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    cins = [r[0] for r in conn.execute("""
        SELECT DISTINCT CIN FROM outreach_analytics WHERE Reply_Received = 1
    """).fetchall()]
    conn.close()
    print(f"Summarizing {len(cins)} replied contact(s)…")
    for cin in cins:
        summarize_contact(cin, db_path)


def main():
    ap = argparse.ArgumentParser(description="Summarize replied-contact email threads")
    ap.add_argument("--cin", help="Summarize one contact by CIN")
    ap.add_argument("--all-replied", action="store_true", help="Summarize every replied contact")
    args = ap.parse_args()
    if args.cin:
        print(summarize_contact(args.cin))
    elif args.all_replied:
        summarize_all_replied()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
