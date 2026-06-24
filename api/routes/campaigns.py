# api/routes/campaigns.py

from fastapi import APIRouter
from typing import Optional
from ..database import get_conn

router = APIRouter()


@router.get("/")
def get_templates(country: Optional[str] = None):
    conn = get_conn()
    cursor = conn.cursor()
    # US arms use the 'us_' Variant_Key prefix; India arms don't.
    c = (country or "").lower()
    where = ""
    if c == "us":
        where = "WHERE Variant_Key LIKE 'us\\_%' ESCAPE '\\'"
    elif c == "india":
        where = "WHERE Variant_Key NOT LIKE 'us\\_%' ESCAPE '\\'"
    cursor.execute(f"""
        SELECT Template_ID, Variant_Key, Segment, Subject_Line,
               Body_HTML, Body_Plain, CTA_URL, Is_Active, Created_At
        FROM campaign_templates
        {where}
        ORDER BY Segment, Variant_Key
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


@router.get("/{template_id}")
def get_template(template_id: int):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM campaign_templates WHERE Template_ID = ?", (template_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {"error": "Not found"}


@router.patch("/{template_id}")
def update_template(template_id: int, body: dict):
    allowed = ["Subject_Line", "Body_HTML", "Body_Plain", "CTA_URL", "Is_Active"]
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        return {"error": "No valid fields to update"}

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values     = list(updates.values()) + [template_id]

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE campaign_templates SET {set_clause} WHERE Template_ID = ?", values
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@router.post("/preview")
def preview_template(body: dict):
    """Renders a template with sample data for preview."""
    template_id = body.get("template_id")
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM campaign_templates WHERE Template_ID = ?", (template_id,))
    t = cursor.fetchone()
    conn.close()

    if not t:
        return {"error": "Template not found"}

    t = dict(t)
    sample = {
        "company_name":       "Acme Retail Pvt Ltd",
        "personalized_sentence": "My analysis shows 8 other retail companies in Maharashtra with your exact capital bracket are currently capturing impression share.",
        "audit_url":          t["CTA_URL"] + "?utm_source=preview&cin=SAMPLE",
        "competitor_count":   "8",
    }

    html = t["Body_HTML"]
    plain = t["Body_Plain"]
    subject = t["Subject_Line"]

    for k, v in sample.items():
        html    = html.replace("{" + k + "}", v)
        plain   = plain.replace("{" + k + "}", v)
        subject = subject.replace("{" + k + "}", v)

    return {
        "subject":    subject,
        "body_html":  html,
        "body_plain": plain,
    }


@router.post("/ab-promote")
def promote_winner(body: dict):
    """Deactivates the losing variant in an A/B pair."""
    winner_key = body.get("winner_variant")
    if not winner_key:
        return {"error": "winner_variant required"}

    # Determine the loser
    if winner_key.endswith('_a'):
        loser_key = winner_key[:-2] + '_b'
    elif winner_key.endswith('_b'):
        loser_key = winner_key[:-2] + '_a'
    else:
        return {"error": "Variant doesn't end with _a or _b"}

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE campaign_templates SET Is_Active = 0 WHERE Variant_Key = ?",
        (loser_key,)
    )
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return {"ok": True, "deactivated": loser_key, "rows_affected": affected}