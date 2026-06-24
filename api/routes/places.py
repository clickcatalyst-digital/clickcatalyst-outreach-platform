# api/routes/places.py
# Lead generation via Google Places API

from fastapi import APIRouter, HTTPException
from ..database import get_conn
from ..services.places_service import search_text, normalize_place

router = APIRouter()


def _upsert_places_lead(cursor, p: dict, source_query: str) -> str:
    """
    Insert or refresh a row in places_leads.
    Returns the synthetic CIN for downstream use.
    """
    cursor.execute("""
        INSERT INTO places_leads (
            Place_ID, CIN, Display_Name, Formatted_Address,
            National_Phone, International_Phone, Phone_Formatted, Website_URI,
            Rating, User_Rating_Count, Business_Status,
            Primary_Type, Types_JSON, Latitude, Longitude,
            Google_Maps_URI, Source_Query, Quality_Score, Quality_Reasons
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(Place_ID) DO UPDATE SET
            Display_Name      = excluded.Display_Name,
            Formatted_Address = excluded.Formatted_Address,
            National_Phone    = COALESCE(excluded.National_Phone, places_leads.National_Phone),
            International_Phone = COALESCE(excluded.International_Phone, places_leads.International_Phone),
            Phone_Formatted   = COALESCE(excluded.Phone_Formatted, places_leads.Phone_Formatted),
            Website_URI       = COALESCE(excluded.Website_URI, places_leads.Website_URI),
            Rating            = excluded.Rating,
            User_Rating_Count = excluded.User_Rating_Count,
            Business_Status   = excluded.Business_Status,
            Source_Query      = excluded.Source_Query,
            Quality_Score     = excluded.Quality_Score,
            Quality_Reasons   = excluded.Quality_Reasons
    """, (
        p["place_id"], p["cin"], p["display_name"], p["formatted_address"],
        p["national_phone"], p["international_phone"], p["phone_formatted"], p["website_uri"],
        p["rating"], p["user_rating_count"], p["business_status"],
        p["primary_type"], p["types_json"], p["latitude"], p["longitude"],
        p["google_maps_uri"], source_query, p["quality_score"], p["quality_reasons"],
    ))
    return p["cin"]

def _upsert_enrichment(cursor, p: dict):
    """
    Mirror Places lead into company_enrichment with synthetic CIN.
    Lets the existing pipeline (queue, email engine, etc.) treat it like any other lead.
    """
    phone = p["national_phone"] or p["international_phone"]
    cursor.execute("""
        INSERT INTO company_enrichment (
            CIN, Website_URL, Phone, Phone_Formatted, Domain_Source,
            Pipeline_Status, Last_Enriched_Date
        ) VALUES (?, ?, ?, ?, 'Google Places', 'Places_Discovered', date('now'))
        ON CONFLICT(CIN) DO UPDATE SET
            Website_URL    = COALESCE(excluded.Website_URL, company_enrichment.Website_URL),
            Phone          = COALESCE(excluded.Phone, company_enrichment.Phone),
            Phone_Formatted = COALESCE(excluded.Phone_Formatted, company_enrichment.Phone_Formatted),
            Last_Enriched_Date = date('now')
    """, (p["cin"], p["website_uri"], phone, p["phone_formatted"]))


@router.post("/search")
def places_search(body: dict):
    """
    Run a Places text search and persist results.
    Body: {
        "query": "PPC agency in Ahmedabad",          # required
        "location_bias": {"lat": 23.02, "lng": 72.57, "radius_m": 30000},  # optional
        "page_token": "...",                          # optional, for pagination
        "max_results": 20,                            # optional, default 20
        "persist": true                               # optional, default true
    }
    """
    query = (body.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")

    location_bias = body.get("location_bias")
    page_token    = body.get("page_token")
    max_results   = body.get("max_results", 20)
    persist       = body.get("persist", True)

    try:
        result = search_text(
            query=query,
            location_bias=location_bias,
            page_token=page_token,
            max_results=max_results,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Places API error: {str(e)}")

    raw_places = result["places"]
    normalized = [normalize_place(p) for p in raw_places if p.get("id")]

    inserted_count = 0
    if persist and normalized:
        conn = get_conn()
        cursor = conn.cursor()
        try:
            for p in normalized:
                _upsert_places_lead(cursor, p, source_query=query)
                _upsert_enrichment(cursor, p)
                inserted_count += 1
            conn.commit()
        finally:
            conn.close()

    # Stats for visibility
    with_phone   = sum(1 for p in normalized if p["national_phone"] or p["international_phone"])
    with_website = sum(1 for p in normalized if p["website_uri"])

    # Log this search to bulk_run_queries (Run_ID NULL = ad-hoc search)
    if persist:
        conn = get_conn()
        try:
            conn.execute("""
                INSERT INTO bulk_run_queries
                    (Run_ID, Query_Text, City, Status, Leads_Returned, Leads_New, Executed_At)
                VALUES (NULL, ?, NULL, 'success', ?, ?, CURRENT_TIMESTAMP)
            """, (query, len(normalized), inserted_count))
            conn.commit()
        finally:
            conn.close()

    return {
        "query": query,
        "count": len(normalized),
        "stats": {
            "with_phone":   with_phone,
            "with_website": with_website,
            "persisted":    inserted_count,
        },
        "next_page_token": result["next_page_token"],
        "leads": normalized,
    }


@router.get("/")
def list_places_leads(
    has_phone:     bool = False,
    has_website:   bool = False,
    business_status: str = None,
    source_query:  str = None,
    min_quality:   int = 0,        # filter by quality threshold
    page:          int = 1,
    limit:         int = 50,
):
    """List Places-sourced leads from the DB with filters."""
    conn = get_conn()
    cursor = conn.cursor()
    offset = (page - 1) * limit

    where  = ["1=1"]
    params = []

    if has_phone:
        where.append("(National_Phone IS NOT NULL OR International_Phone IS NOT NULL)")
    if has_website:
        where.append("Website_URI IS NOT NULL")
    if business_status:
        where.append("Business_Status = ?")
        params.append(business_status)
    if source_query:
        where.append("Source_Query LIKE ?")
        params.append(f"%{source_query}%")
    if min_quality > 0:
        where.append("Quality_Score >= ?")
        params.append(min_quality)

    where_clause = " AND ".join(where)

    cursor.execute(f"""
        SELECT
            Place_ID, CIN, Display_Name, Formatted_Address,
            National_Phone, International_Phone, Phone_Formatted, Website_URI,
            Rating, User_Rating_Count, Business_Status,
            Primary_Type, Latitude, Longitude, Google_Maps_URI,
            Source_Query, Discovered_At, Quality_Score, Quality_Reasons
        FROM places_leads
        WHERE {where_clause}
        ORDER BY Quality_Score DESC, Rating DESC NULLS LAST, User_Rating_Count DESC
        LIMIT ? OFFSET ?
    """, params + [limit, offset])

    leads = [dict(r) for r in cursor.fetchall()]

    cursor.execute(f"SELECT COUNT(*) FROM places_leads WHERE {where_clause}", params)
    total = cursor.fetchone()[0]

    conn.close()
    return {"leads": leads, "total": total, "page": page, "limit": limit}


@router.get("/{place_id}")
def get_place_detail(place_id: str):
    """Get full detail for one Places lead, including enrichment join."""
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            p.*,
            e.Pipeline_Status, e.Has_Google_Ads_Pixel, e.Has_GMB,
            e.Email_Sent_Date, e.Audit_Link_Clicked
        FROM places_leads p
        LEFT JOIN company_enrichment e ON p.CIN = e.CIN
        WHERE p.Place_ID = ?
    """, (place_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"error": "Place not found"}
    return {"lead": dict(row)}


@router.get("/with-interactions/list")
def list_with_interactions(
    tab:          str = "to_call",     # 'to_call' | 'contacted'
    search:       str = None,
    city:         str = None,
    min_quality:  int = 0,
    has_phone:    bool = True,         # phone tab only cares about callable leads
    pixel:        str = None,          # 'yes' | 'no' | 'unchecked' | None (all)
    page:         int = 1,
    limit:        int = 50,
):
    """
    List Places leads joined with interaction summary.
    'to_call'    => leads with no interactions yet (or only Interacted=0 ones)
    'contacted'  => leads that have at least one Interacted=1 record
    """
    conn = get_conn()
    cursor = conn.cursor()
    offset = (page - 1) * limit

    where  = ["1=1"]
    params = []

    if has_phone:
        where.append("p.Phone_Formatted IS NOT NULL")
    if min_quality > 0:
        where.append("p.Quality_Score >= ?")
        params.append(min_quality)
    if search:
        where.append("p.Display_Name LIKE ?")
        params.append(f"%{search}%")
    if city:
        where.append("p.Formatted_Address LIKE ?")
        params.append(f"%{city}%")
    if pixel == "yes":
        where.append("EXISTS (SELECT 1 FROM company_enrichment e WHERE e.CIN = p.CIN AND e.Has_Google_Ads_Pixel = 1)")
    elif pixel == "no":
        where.append("EXISTS (SELECT 1 FROM company_enrichment e WHERE e.CIN = p.CIN AND e.Has_Google_Ads_Pixel = 0)")
    elif pixel == "unchecked":
        where.append("EXISTS (SELECT 1 FROM company_enrichment e WHERE e.CIN = p.CIN AND e.Has_Google_Ads_Pixel IS NULL)")

    # Tab filter
    if tab == "contacted":
        where.append("""EXISTS (
            SELECT 1 FROM lead_interactions i
            WHERE i.CIN = p.CIN AND i.Interacted = 1
        )""")
    else:  # to_call
        where.append("""NOT EXISTS (
            SELECT 1 FROM lead_interactions i
            WHERE i.CIN = p.CIN AND i.Interacted = 1
        )""")

    where_clause = " AND ".join(where)

    cursor.execute(f"""
        SELECT
            p.Place_ID, p.CIN, p.Display_Name, p.Formatted_Address,
            p.Phone_Formatted, p.National_Phone, p.Website_URI,
            p.Rating, p.User_Rating_Count, p.Quality_Score,
            p.Source_Query, p.Google_Maps_URI,
            e.Has_Google_Ads_Pixel,
            (SELECT COUNT(*) FROM lead_interactions i WHERE i.CIN = p.CIN) AS Interaction_Count,
            (SELECT MAX(Created_At) FROM lead_interactions i WHERE i.CIN = p.CIN) AS Last_Interaction_At,
            (SELECT Comment FROM lead_interactions i WHERE i.CIN = p.CIN ORDER BY Created_At DESC LIMIT 1) AS Last_Comment
        FROM places_leads p
        LEFT JOIN company_enrichment e ON p.CIN = e.CIN
        WHERE {where_clause}
        ORDER BY p.Quality_Score DESC, p.User_Rating_Count DESC
        LIMIT ? OFFSET ?
    """, params + [limit, offset])

    leads = [dict(r) for r in cursor.fetchall()]

    cursor.execute(f"SELECT COUNT(*) FROM places_leads p WHERE {where_clause}", params)
    total = cursor.fetchone()[0]

    # Tab counts (always show both, regardless of current tab)
    base_filters = ["p.Phone_Formatted IS NOT NULL"] if has_phone else ["1=1"]
    base_clause = " AND ".join(base_filters)

    cursor.execute(f"""
        SELECT
          (SELECT COUNT(*) FROM places_leads p
            WHERE {base_clause}
            AND NOT EXISTS (SELECT 1 FROM lead_interactions i WHERE i.CIN = p.CIN AND i.Interacted = 1)) AS to_call,
          (SELECT COUNT(*) FROM places_leads p
            WHERE {base_clause}
            AND EXISTS (SELECT 1 FROM lead_interactions i WHERE i.CIN = p.CIN AND i.Interacted = 1)) AS contacted
    """)
    counts_row = cursor.fetchone()
    counts = {"to_call": counts_row[0], "contacted": counts_row[1]}

    cursor.execute("""
        SELECT DISTINCT
            CASE
                WHEN Formatted_Address LIKE '%Mumbai%' THEN 'Mumbai'
                WHEN Formatted_Address LIKE '%Bengaluru%' OR Formatted_Address LIKE '%Bangalore%' THEN 'Bangalore'
                WHEN Formatted_Address LIKE '%Ahmedabad%' THEN 'Ahmedabad'
                WHEN Formatted_Address LIKE '%Delhi%' THEN 'Delhi'
                WHEN Formatted_Address LIKE '%Pune%' THEN 'Pune'
                WHEN Formatted_Address LIKE '%Hyderabad%' THEN 'Hyderabad'
                ELSE NULL
            END AS city
        FROM places_leads
        WHERE Phone_Formatted IS NOT NULL
    """)
    cities = sorted([r["city"] for r in cursor.fetchall() if r["city"]])

    conn.close()
    return {
        "leads": leads,
        "total": total,
        "page": page,
        "limit": limit,
        "counts": counts,
        "cities": cities,
    }


@router.post("/recheck-pixel/{cin}")
def recheck_pixel(cin: str):
    """Force re-run pixel check on a single lead."""
    from ..services.pixel_service import check_and_persist

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT Website_URL FROM company_enrichment WHERE CIN = ?
    """, (cin,))
    row = cursor.fetchone()
    conn.close()

    if not row or not row["Website_URL"]:
        raise HTTPException(status_code=404, detail="Lead not found or no website")

    result = check_and_persist(cin, row["Website_URL"])
    return {
        "cin": cin,
        "has_pixel": result.has_pixel,
        "method": result.method,
        "error": result.error,
    }


@router.post("/recheck-pixel/bulk/unchecked")
def recheck_unchecked_bulk(body: dict = None):
    """
    Re-run pixel check on all leads where Has_Google_Ads_Pixel IS NULL
    (either never checked or previous check failed).
    Body: {"min_quality": 40} (optional override)
    """
    from ..services.pixel_service import check_places_leads_batch
    body = body or {}
    min_quality = body.get("min_quality")
    summary = check_places_leads_batch(min_quality=min_quality, only_unchecked=True)
    return {"ok": True, **summary}