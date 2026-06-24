# api/routes/contacts.py

from fastapi import APIRouter
from ..database import get_conn

router = APIRouter()

@router.get("/{cin}")
def get_contacts(cin: str):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT Contact_ID, CIN, Full_Name, Job_Title,
               Email_Address, Email_Label, LinkedIn_URL,
               Is_Primary_Contact, Added_Date
        FROM company_contacts
        WHERE CIN = ?
        ORDER BY Is_Primary_Contact DESC, Contact_ID ASC
    """, (cin,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


@router.post("/{cin}")
def add_contact(cin: str, body: dict):
    required = ["full_name", "email_address"]
    for f in required:
        if not body.get(f):
            return {"error": f"{f} is required"}

    conn = get_conn()
    cursor = conn.cursor()

    if body.get("is_primary"):
        cursor.execute(
            "UPDATE company_contacts SET Is_Primary_Contact = 0 WHERE CIN = ?", (cin,)
        )

    cursor.execute("""
        INSERT INTO company_contacts
            (CIN, Full_Name, Job_Title, Email_Address, Email_Label,
             LinkedIn_URL, Is_Primary_Contact)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        cin,
        body["full_name"].strip(),
        body.get("job_title"),
        body["email_address"].strip(),
        body.get("email_label", "Work"),
        body.get("linkedin_url") or None,
        int(bool(body.get("is_primary", False)))
    ))
    conn.commit()
    contact_id = cursor.lastrowid
    conn.close()
    return {"ok": True, "contact_id": contact_id}


@router.patch("/{cin}/primary/{contact_id}")
def set_primary(cin: str, contact_id: int):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("UPDATE company_contacts SET Is_Primary_Contact = 0 WHERE CIN = ?", (cin,))
    cursor.execute("UPDATE company_contacts SET Is_Primary_Contact = 1 WHERE Contact_ID = ?", (contact_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.delete("/{cin}/{contact_id}")
def delete_contact(cin: str, contact_id: int):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM company_contacts WHERE Contact_ID = ? AND CIN = ?", (contact_id, cin))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.patch("/{cin}/skip")
def skip_lead(cin: str):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE company_enrichment
        SET Pipeline_Status = 'No_Contact_Found'
        WHERE CIN = ?
    """, (cin,))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.post("/bulk")
def bulk_import(body: dict):
    """
    Bulk import contacts from CSV data.
    Expects: { "contacts": [ { cin, full_name, job_title, email_address, email_label, linkedin_url, is_primary }, ... ] }
    """
    contacts = body.get("contacts", [])
    if not contacts:
        return {"error": "No contacts provided", "imported": 0, "skipped": 0}

    conn = get_conn()
    cursor = conn.cursor()
    imported = 0
    skipped = 0
    errors = []

    for i, c in enumerate(contacts):
        cin = (c.get("cin") or "").strip()
        full_name = (c.get("full_name") or "").strip()
        email = (c.get("email_address") or "").strip()

        if not cin or not full_name or not email or "@" not in email:
            skipped += 1
            errors.append(f"Row {i+1}: missing CIN, name, or valid email")
            continue

        # Verify CIN exists
        cursor.execute("SELECT CIN FROM vw_qualified_leads WHERE CIN = ?", (cin,))
        if not cursor.fetchone():
            skipped += 1
            errors.append(f"Row {i+1}: CIN {cin} not found in database")
            continue

        is_primary = int(bool(c.get("is_primary", False)))
        if is_primary:
            cursor.execute("UPDATE company_contacts SET Is_Primary_Contact = 0 WHERE CIN = ?", (cin,))

        cursor.execute("""
            INSERT INTO company_contacts
                (CIN, Full_Name, Job_Title, Email_Address, Email_Label, LinkedIn_URL, Is_Primary_Contact)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            cin, full_name,
            (c.get("job_title") or "").strip() or None,
            email,
            (c.get("email_label") or "Work").strip(),
            (c.get("linkedin_url") or "").strip() or None,
            is_primary
        ))
        imported += 1

    conn.commit()
    conn.close()
    return {"ok": True, "imported": imported, "skipped": skipped, "errors": errors[:20]}