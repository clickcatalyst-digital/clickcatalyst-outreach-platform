# us_lead_engine/apollo_client.py
# Apollo REST wrapper. search() is free; enrich() costs exactly 1 credit per match.
# Mirrors the endpoints validated live via the Apollo MCP on 2026-06-20.

import requests

from .config import APOLLO_API_KEY, APOLLO_BASE
from . import cost_tracker

HEADERS = {
    "Content-Type": "application/json",
    "Cache-Control": "no-cache",
    "x-api-key": APOLLO_API_KEY,
}

MASKED_EMAIL_MARKER = "email_not_unlocked"   # Apollo returns this until you reveal


def search(filters: dict, page: int = 1):
    """
    POST mixed_people/api_search — FREE (the API-optimized People Search endpoint).
    Returns (people: list, total: int). Emails are masked; use enrich() to reveal.
    Note: api_search may require a *master* API key (generate in Apollo settings).
    """
    body = {**filters, "page": page}
    resp = requests.post(
        f"{APOLLO_BASE}/mixed_people/api_search",
        json=body, headers=HEADERS, timeout=30,
    )
    if not resp.ok:
        print("STATUS:", resp.status_code)
        print("REQUEST BODY:", body)
        print("RESPONSE:", resp.text)

    resp.raise_for_status()
    data = resp.json()

    people = data.get("people", []) + data.get("contacts", [])
    # total_entries appears top-level on some responses, under pagination on others
    total = (data.get("total_entries")
             or (data.get("pagination") or {}).get("total_entries")
             or len(people))

    cost_tracker.log_call(
        endpoint="mixed_people/api_search", call_type="search",
        credits_used=0, results_returned=len(people),
        notes=f"page={page} total={total}",
    )
    return people, total


def enrich(person_id=None, first_name=None, last_name=None,
           organization_name=None, domain=None):
    """
    POST people/match — COSTS 1 CREDIT per matched person (0 if not found).
    Returns the person dict with revealed email + last name, or None if not found.
    Only call this AFTER a lead has passed qualification.
    """
    body = {"reveal_personal_emails": False}
    if person_id:         body["id"] = person_id
    if first_name:        body["first_name"] = first_name
    if last_name:         body["last_name"] = last_name
    if organization_name: body["organization_name"] = organization_name
    if domain:            body["domain"] = domain

    resp = requests.post(
        f"{APOLLO_BASE}/people/match",
        json=body, headers=HEADERS, timeout=30,
    )
    if not resp.ok:
        print("STATUS:", resp.status_code)
        print("REQUEST BODY:", body)
        print("RESPONSE:", resp.text)

    resp.raise_for_status()
    person = resp.json().get("person")

    email = (person or {}).get("email") or ""
    revealed = bool(person) and email and MASKED_EMAIL_MARKER not in email
    matched = bool(person)

    cost_tracker.log_call(
        endpoint="people/match", call_type="reveal",
        credits_used=1 if matched else 0,
        results_returned=1 if matched else 0,
        emails_revealed=1 if revealed else 0,
        notes=f"id={person_id or ''} matched={matched} revealed={revealed}",
    )
    return person if revealed else None
