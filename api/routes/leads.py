# api/routes/leads.py

from fastapi import APIRouter, Query
from typing import Optional
from ..database import get_conn

router = APIRouter()


@router.get("/")
def get_leads(
    segment: Optional[str] = None,
    status:  Optional[str] = None,
    search:  Optional[str] = None,
    country: Optional[str] = None,   # 'us' = Apollo leads; else India/MCA (default)
    page:    int = 1,
    limit:   int = 50
):
    conn   = get_conn()
    cursor = conn.cursor()
    offset = (page - 1) * limit

    # --- US (Apollo) leads live in company_enrichment, NOT vw_qualified_leads ---
    if (country or "").lower() == "us":
        uwhere  = ["e.Lead_Source = 'US_Apollo'"]
        uparams = []
        if status:
            uwhere.append("e.Pipeline_Status = ?"); uparams.append(status)
        if search:
            uwhere.append("(e.Company_Name LIKE ? OR e.CIN LIKE ?)")
            uparams += [f"%{search}%", f"%{search}%"]
        uwc = " AND ".join(uwhere)
        cursor.execute(f"""
            SELECT
                e.CIN,
                e.Company_Name AS CompanyName,
                'US Agency'    AS ICP_Segment,
                NULL AS State, NULL AS PaidupCapital, NULL AS RegistrationDate, NULL AS nic_code,
                e.Website_URL, e.Domain_Source, e.Has_GMB, e.Has_Google_Ads_Pixel,
                e.Pipeline_Status, NULL AS Competitor_Count, e.Email_Sent_Date,
                (SELECT COUNT(*) FROM company_contacts cc WHERE cc.CIN = e.CIN) AS Contact_Count
            FROM company_enrichment e
            WHERE {uwc}
            ORDER BY e.CIN
            LIMIT ? OFFSET ?
        """, uparams + [limit, offset])
        leads = [dict(r) for r in cursor.fetchall()]
        cursor.execute(f"SELECT COUNT(*) FROM company_enrichment e WHERE {uwc}", uparams)
        total = cursor.fetchone()[0]
        conn.close()
        return {"leads": leads, "total": total, "page": page, "limit": limit}

    where  = ["1=1"]
    params = []

    if segment:
        where.append("q.ICP_Segment = ?")
        params.append(segment)

    if status:
        where.append("e.Pipeline_Status = ?")
        params.append(status)

    if search:
        where.append("(q.CompanyName LIKE ? OR q.CIN LIKE ?)")
        params += [f"%{search}%", f"%{search}%"]

    where_clause = " AND ".join(where)

    cursor.execute(f"""
        SELECT
            q.CIN,
            q.CompanyName,
            q.ICP_Segment,
            q.State,
            q.PaidupCapital,
            q.RegistrationDate,
            q.nic_code,
            e.Website_URL,
            e.Domain_Source,
            e.Has_GMB,
            e.Has_Google_Ads_Pixel,
            e.Pipeline_Status,
            e.Competitor_Count,
            e.Email_Sent_Date,
            (SELECT COUNT(*) FROM company_contacts cc WHERE cc.CIN = q.CIN) AS Contact_Count
        FROM vw_qualified_leads q
        LEFT JOIN company_enrichment e ON q.CIN = e.CIN
        WHERE {where_clause}
        ORDER BY q.PaidupCapital DESC
        LIMIT ? OFFSET ?
    """, params + [limit, offset])

    leads = [dict(r) for r in cursor.fetchall()]

    # Total count for pagination
    cursor.execute(f"""
        SELECT COUNT(*)
        FROM vw_qualified_leads q
        LEFT JOIN company_enrichment e ON q.CIN = e.CIN
        WHERE {where_clause}
    """, params)
    total = cursor.fetchone()[0]

    conn.close()
    return {"leads": leads, "total": total, "page": page, "limit": limit}


@router.get("/segments")
def get_segments():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ICP_Segment, COUNT(*) as count
        FROM vw_qualified_leads
        GROUP BY ICP_Segment
        ORDER BY count DESC
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


@router.get("/statuses")
def get_statuses():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT Pipeline_Status, COUNT(*) as count
        FROM company_enrichment
        GROUP BY Pipeline_Status
        ORDER BY count DESC
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


@router.get("/{cin}")
def get_lead_detail(cin: str):
    conn = get_conn()
    cursor = conn.cursor()

    if cin.startswith("APOLLO_"):
        # US (Apollo) lead — not in vw_qualified_leads.
        cursor.execute("""
            SELECT
                e.CIN, e.Company_Name AS CompanyName, 'US Agency' AS ICP_Segment,
                NULL AS State, NULL AS PaidupCapital, NULL AS RegistrationDate,
                NULL AS nic_code, NULL AS Industry,
                e.Website_URL, e.Domain_Source, e.Has_GMB,
                e.Has_Google_Ads_Pixel, e.Pipeline_Status,
                NULL AS Competitor_Count, e.Personalized_Sentence,
                e.Email_Sent_Date, e.Audit_Link_Clicked
            FROM company_enrichment e
            WHERE e.CIN = ?
        """, (cin,))
    else:
        cursor.execute("""
            SELECT
                q.CIN, q.CompanyName, q.ICP_Segment, q.State,
                q.PaidupCapital, q.RegistrationDate, q.nic_code,
                n.description AS Industry,
                e.Website_URL, e.Domain_Source, e.Has_GMB,
                e.Has_Google_Ads_Pixel, e.Pipeline_Status,
                e.Competitor_Count, e.Personalized_Sentence,
                e.Email_Sent_Date, e.Audit_Link_Clicked
            FROM vw_qualified_leads q
            LEFT JOIN company_enrichment e ON q.CIN = e.CIN
            LEFT JOIN nic_master n ON q.nic_code = n.nic_code_5d
            WHERE q.CIN = ?
        """, (cin,))
    lead = cursor.fetchone()

    if not lead:
        conn.close()
        return {"error": "Lead not found"}

    # Contacts
    cursor.execute("""
        SELECT Contact_ID, Full_Name, Job_Title, Email_Address,
               Email_Label, LinkedIn_URL, Is_Primary_Contact, Added_Date
        FROM company_contacts
        WHERE CIN = ?
        ORDER BY Is_Primary_Contact DESC
    """, (cin,))
    contacts = [dict(r) for r in cursor.fetchall()]

    # Outreach history
    cursor.execute("""
        SELECT Analytics_ID, Email_Sent_Date, Batch_ID,
               Campaign_Variant, Subject_Line,
               Audit_Link_Clicked, Clicked_At, Email_Opened
        FROM outreach_analytics
        WHERE CIN = ?
        ORDER BY Analytics_ID DESC
    """, (cin,))
    outreach = [dict(r) for r in cursor.fetchall()]

    conn.close()
    return {
        "lead":     dict(lead),
        "contacts": contacts,
        "outreach": outreach
    }


@router.patch("/{cin}/website")
def update_website(cin: str, body: dict):
    url = body.get("website_url", "").strip()
    if not url:
        return {"error": "website_url is required"}
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE company_enrichment
        SET Website_URL = ?, Domain_Source = 'Manual Override'
        WHERE CIN = ?
    """, (url, cin))
    conn.commit()
    conn.close()
    return {"ok": True, "website_url": url}


@router.get("/queue/next")
def get_next_in_queue(offset: int = 0):
    """Returns the next Intelligence_Ready lead without contacts."""
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            q.CIN, q.CompanyName, q.ICP_Segment, q.State,
            q.PaidupCapital, q.nic_code,
            e.Website_URL, e.Domain_Source, e.Has_GMB,
            e.Has_Google_Ads_Pixel, e.Pipeline_Status,
            e.Competitor_Count, e.Personalized_Sentence,
            (SELECT COUNT(*) FROM company_contacts cc WHERE cc.CIN = q.CIN) AS Contact_Count
        FROM vw_qualified_leads q
        JOIN company_enrichment e ON q.CIN = e.CIN
        WHERE e.Pipeline_Status IN ('Intelligence_Ready', 'Enriched_Ready')
          AND q.CIN NOT IN (SELECT DISTINCT CIN FROM company_contacts)
          AND e.Pipeline_Status != 'No_Contact_Found'
        ORDER BY q.PaidupCapital DESC
        LIMIT 1 OFFSET ?
    """, (offset,))

    row = cursor.fetchone()

    # Total remaining in queue
    cursor.execute("""
        SELECT COUNT(*)
        FROM vw_qualified_leads q
        JOIN company_enrichment e ON q.CIN = e.CIN
        WHERE e.Pipeline_Status IN ('Intelligence_Ready', 'Enriched_Ready')
          AND q.CIN NOT IN (SELECT DISTINCT CIN FROM company_contacts)
          AND e.Pipeline_Status != 'No_Contact_Found'
    """)
    total = cursor.fetchone()[0]

    conn.close()

    if not row:
        return {"lead": None, "total": total, "offset": offset}

    return {"lead": dict(row), "total": total, "offset": offset}