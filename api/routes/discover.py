# api/routes/discover.py
# Async lead discovery: jobs, history, quota tracking.

from fastapi import APIRouter, BackgroundTasks, HTTPException
from datetime import datetime
import json
from pathlib import Path

from ..database import get_conn
from ..services.places_service import search_text, normalize_place
from .places import _upsert_places_lead, _upsert_enrichment

router = APIRouter()

# Load cities config once (for location_bias when city_hint provided)
_CITIES_PATH = Path("configs/cities.json")
_CITIES = json.loads(_CITIES_PATH.read_text()) if _CITIES_PATH.exists() else {}

# Quota constants
FREE_TIER_PRO_PER_MONTH = 5000   # Google's Pro SKU free monthly events


# --- Quota and history -------------------------------------------------

@router.get("/summary")
def discover_summary():
    """
    Returns:
      - quota: searches used this month, free tier remaining
      - history: past searches with leads found
      - cities: available city presets
    """
    conn = get_conn()
    cursor = conn.cursor()

    # Quota: count searches done this calendar month
    cursor.execute("""
        SELECT COUNT(*) FROM bulk_run_queries
        WHERE Status = 'success'
          AND Executed_At >= date('now', 'start of month')
    """)
    used_this_month = cursor.fetchone()[0] or 0

    # History: past discover jobs + bulk runner queries (unified view)
    # Show last 50, most recent first
    cursor.execute("""
        SELECT
            Query_Text,
            MAX(Executed_At) AS last_run,
            COUNT(*) AS run_count,
            SUM(Leads_Returned) AS total_leads,
            SUM(Leads_New) AS total_new
        FROM bulk_run_queries
        WHERE Status = 'success'
        GROUP BY LOWER(TRIM(Query_Text))
        ORDER BY last_run DESC
        LIMIT 50
    """)
    history = [dict(r) for r in cursor.fetchall()]

    # Active jobs (pending/running)
    cursor.execute("""
        SELECT Job_ID, Query_Text, City_Hint, Status, Created_At,
               Leads_Returned, Leads_New
        FROM discover_jobs
        WHERE Status IN ('pending', 'running')
        ORDER BY Created_At DESC
    """)
    active_jobs = [dict(r) for r in cursor.fetchall()]

    # Recently completed jobs (for "just finished" toasts in UI)
    cursor.execute("""
        SELECT Job_ID, Query_Text, City_Hint, Status, Finished_At,
               Leads_Returned, Leads_New, Leads_HighQ, Error_Message
        FROM discover_jobs
        WHERE Status IN ('done', 'failed')
        ORDER BY Finished_At DESC
        LIMIT 5
    """)
    recent_jobs = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return {
        "quota": {
            "used_this_month": used_this_month,
            "free_tier_limit": FREE_TIER_PRO_PER_MONTH,
            "remaining": max(0, FREE_TIER_PRO_PER_MONTH - used_this_month),
            "percent_used": round((used_this_month / FREE_TIER_PRO_PER_MONTH) * 100, 1),
        },
        "history": history,
        "active_jobs": active_jobs,
        "recent_jobs": recent_jobs,
        "cities": [{"key": k, **v} for k, v in _CITIES.items()],
    }


# --- Job execution ------------------------------------------------------

def _execute_job(job_id: int, query: str, city_hint: str | None):
    """Background task that actually runs the search, then chains pixel check."""
    conn = get_conn()
    cursor = conn.cursor()
    new_cins = []  # collected for downstream pixel check

    try:
        cursor.execute("""
            UPDATE discover_jobs SET Status = 'running', Started_At = CURRENT_TIMESTAMP
            WHERE Job_ID = ?
        """, (job_id,))
        conn.commit()

        # Resolve location_bias
        location_bias = None
        if city_hint and city_hint in _CITIES:
            c = _CITIES[city_hint]
            location_bias = {
                "lat": c["lat"], "lng": c["lng"], "radius_m": c["radius_m"]
            }

        # Run the search
        result = search_text(query=query, location_bias=location_bias, max_results=20)
        places = result.get("places", [])

        # Persist
        leads_new = 0
        leads_highq = 0
        existing_ids = {r["Place_ID"] for r in cursor.execute(
            "SELECT Place_ID FROM places_leads"
        ).fetchall()}

        for raw in places:
            normalized = normalize_place(raw)
            if not normalized:
                continue
            if normalized["place_id"] not in existing_ids:
                leads_new += 1
                new_cins.append(normalized["cin"])  # track for pixel check
            if (normalized.get("quality_score") or 0) >= 70:
                leads_highq += 1
            _upsert_places_lead(cursor, normalized, source_query=query)
            _upsert_enrichment(cursor, normalized)

        # Log the search to bulk_run_queries (for quota tracking)
        cursor.execute("""
            INSERT INTO bulk_run_queries
                (Run_ID, Query_Text, City, Status, Leads_Returned, Leads_New, Executed_At)
            VALUES (NULL, ?, ?, 'success', ?, ?, CURRENT_TIMESTAMP)
        """, (query, city_hint, len(places), leads_new))

        # Mark job done
        cursor.execute("""
            UPDATE discover_jobs
            SET Status = 'done', Finished_At = CURRENT_TIMESTAMP,
                Leads_Returned = ?, Leads_New = ?, Leads_HighQ = ?
            WHERE Job_ID = ?
        """, (len(places), leads_new, leads_highq, job_id))
        conn.commit()
        conn.close()

    except Exception as e:
        cursor.execute("""
            UPDATE discover_jobs
            SET Status = 'failed', Finished_At = CURRENT_TIMESTAMP, Error_Message = ?
            WHERE Job_ID = ?
        """, (str(e)[:500], job_id))
        conn.commit()
        conn.close()
        return

    # Pixel check on new leads (outside try/except so failures here don't mark Places job as failed)
    if new_cins:
        try:
            from ..services.pixel_service import check_places_leads_batch
            check_places_leads_batch(cins=new_cins, max_workers=10)
            print(f"[discover/{job_id}] Pixel enrichment ran on {len(new_cins)} new leads")
        except Exception as pe:
            print(f"[discover/{job_id}] Pixel enrichment failed: {pe}")

@router.post("/run")
def enqueue_search(body: dict, background_tasks: BackgroundTasks):
    """
    Enqueue a discover job. Returns immediately with job_id.
    Body: { "query": "PPC agency in Mumbai", "city_hint": "mumbai" }
    """
    query = (body.get("query") or "").strip()
    city_hint = body.get("city_hint")

    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    if len(query) > 200:
        raise HTTPException(status_code=400, detail="query too long")

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO discover_jobs (Query_Text, City_Hint, Status)
        VALUES (?, ?, 'pending')
    """, (query, city_hint))
    job_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Schedule the actual work as a background task
    background_tasks.add_task(_execute_job, job_id, query, city_hint)

    return {"job_id": job_id, "status": "pending"}


@router.get("/jobs/{job_id}")
def get_job(job_id: int):
    """Poll for job status."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT Job_ID, Query_Text, City_Hint, Status,
               Created_At, Started_At, Finished_At,
               Leads_Returned, Leads_New, Leads_HighQ, Error_Message
        FROM discover_jobs
        WHERE Job_ID = ?
    """, (job_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return dict(row)


@router.get("/check-keyword")
def check_keyword(query: str):
    """
    Returns when a keyword was last searched, if ever.
    Used for soft warning before re-running.
    """
    if not query.strip():
        return {"exists": False}

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT MAX(Executed_At) AS last_run,
               COUNT(*) AS run_count,
               SUM(Leads_Returned) AS total_leads
        FROM bulk_run_queries
        WHERE LOWER(TRIM(Query_Text)) = LOWER(TRIM(?))
          AND Status = 'success'
    """, (query,))
    row = dict(cursor.fetchone())
    conn.close()

    if not row.get("last_run"):
        return {"exists": False}

    return {
        "exists": True,
        "last_run": row["last_run"],
        "run_count": row["run_count"],
        "total_leads": row["total_leads"] or 0,
    }