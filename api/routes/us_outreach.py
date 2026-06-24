# api/routes/us_outreach.py
# Control surface for the US outreach orchestrator (status, config, test emails,
# alerts, manual cycle trigger). The dashboard US Outreach page drives these.

from fastapi import APIRouter, BackgroundTasks, HTTPException

from us_lead_engine import orchestrator, sender
from us_lead_engine.orchestrator import _conn, get_config, set_config

# Ensure the orchestrator tables exist on API startup (idempotent, quiet).
try:
    orchestrator.ensure_tables()
except Exception as _e:  # pragma: no cover
    print(f"[us_outreach] ensure_tables failed: {_e}")

router = APIRouter()

ALLOWED = {
    "mode", "enabled", "test_count", "start_hour", "end_hour", "send_days",
    "replenish_threshold", "replenish_enrich_batch", "monthly_enrich_cap",
    "cycle_minutes", "start_date", "learning_threshold",
}


@router.get("/status")
def us_status():
    return orchestrator.status()


@router.get("/config")
def us_get_config():
    return get_config()


@router.patch("/config")
def us_patch_config(body: dict):
    updated = []
    for k, v in body.items():
        if k in ALLOWED:
            set_config(k, v)
            updated.append(k)
    return {"ok": True, "updated": updated}


@router.get("/test-emails")
def list_test_emails():
    conn = _conn()
    rows = [dict(r) for r in conn.execute(
        "SELECT ID, Email, Added_At FROM us_test_emails ORDER BY ID"
    ).fetchall()]
    conn.close()
    return rows


@router.post("/test-emails")
def add_test_email(body: dict):
    email = (body.get("email") or "").strip()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="valid email required")
    conn = _conn()
    conn.execute("INSERT OR IGNORE INTO us_test_emails (Email) VALUES (?)", (email,))
    conn.commit()
    conn.close()
    return {"ok": True, "email": email}


@router.delete("/test-emails/{eid}")
def del_test_email(eid: int):
    conn = _conn()
    conn.execute("DELETE FROM us_test_emails WHERE ID = ?", (eid,))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.get("/contacts")
def list_us_contacts(search: str = None, page: int = 1, limit: int = 100):
    """US (Apollo) contacts + enrichment + per-contact engagement + notes/summary."""
    from us_lead_engine.summarizer import ensure_contact_columns
    conn = _conn()
    ensure_contact_columns(conn)
    cur = conn.cursor()
    where = ["e.Lead_Source = 'US_Apollo'"]
    params = []
    if search:
        where.append("(e.Company_Name LIKE ? OR cc.Full_Name LIKE ? OR cc.Email_Address LIKE ?)")
        params += [f"%{search}%", f"%{search}%", f"%{search}%"]
    wc = " AND ".join(where)
    offset = (page - 1) * limit
    cur.execute(f"""
        SELECT cc.Contact_ID, cc.CIN, cc.Full_Name, cc.Job_Title, cc.Email_Address,
               cc.Email_Label, cc.LinkedIn_URL, cc.Is_Primary_Contact,
               cc.Notes, cc.Conversation_Summary, cc.Summary_Updated_At,
               e.Company_Name, e.Website_URL, e.Has_Google_Ads_Pixel,
               e.Pipeline_Status, e.Phone, e.Email_Sent_Date,
               (SELECT COUNT(*) FROM outreach_analytics oa WHERE oa.CIN = cc.CIN
                  AND oa.Email_Opened = 1 AND oa.Batch_ID NOT LIKE 'ustest%') AS Opens,
               (SELECT COUNT(*) FROM outreach_analytics oa WHERE oa.CIN = cc.CIN
                  AND oa.Audit_Link_Clicked = 1 AND oa.Batch_ID NOT LIKE 'ustest%') AS Clicks,
               (SELECT COUNT(*) FROM outreach_analytics oa WHERE oa.CIN = cc.CIN
                  AND oa.Reply_Received = 1 AND oa.Batch_ID NOT LIKE 'ustest%') AS Replies
        FROM company_contacts cc
        JOIN company_enrichment e ON cc.CIN = e.CIN
        WHERE {wc}
        ORDER BY e.Company_Name, cc.Is_Primary_Contact DESC
        LIMIT ? OFFSET ?
    """, params + [limit, offset])
    rows = [dict(r) for r in cur.fetchall()]
    cur.execute(f"""
        SELECT COUNT(*) FROM company_contacts cc
        JOIN company_enrichment e ON cc.CIN = e.CIN WHERE {wc}
    """, params)
    total = cur.fetchone()[0]
    conn.close()
    return {"contacts": rows, "total": total}


@router.patch("/contacts/{contact_id}/notes")
def save_contact_notes(contact_id: int, body: dict):
    """Manual research/conversation notes — independent of the AI summary."""
    from us_lead_engine.summarizer import ensure_contact_columns
    conn = _conn()
    ensure_contact_columns(conn)
    conn.execute("UPDATE company_contacts SET Notes = ? WHERE Contact_ID = ?",
                 (body.get("notes") or "", contact_id))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.post("/contacts/{cin}/summarize")
def summarize_contact_now(cin: str):
    """On-demand Gemma summary of the email thread (needs OPENROUTER_API_KEY + Gmail OAuth)."""
    from us_lead_engine import summarizer
    summary = summarizer.summarize_contact(cin)
    return {"ok": bool(summary), "summary": summary}


@router.post("/run-once")
def run_once(background_tasks: BackgroundTasks):
    """Trigger one orchestrator cycle now, bypassing the start-date/window gates (UI test)."""
    background_tasks.add_task(orchestrator.run_cycle, False, True)  # verbose=False, force=True
    return {"ok": True, "message": "cycle triggered"}
