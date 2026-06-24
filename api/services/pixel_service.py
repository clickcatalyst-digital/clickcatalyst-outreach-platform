# api/services/pixel_service.py
# Wraps pixel_checker_02.py for use in API/Discover flows.
# Keeps the original script untouched.

import os
import sys
import concurrent.futures
from typing import Optional

# Ensure project root is on path so we can import the script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pixel_checker_02 import check_pixel as _check_pixel_single, PixelResult
from ..database import get_conn


# Configurable threshold (default 40, override via env var)
PIXEL_CHECK_MIN_QUALITY = int(os.getenv("PIXEL_CHECK_MIN_QUALITY", "40"))


def check_one(url: str) -> PixelResult:
    """Public wrapper — pass-through to the underlying checker."""
    return _check_pixel_single(url)


def check_and_persist(cin: str, url: str) -> PixelResult:
    """Run pixel check on URL and write result to company_enrichment."""
    result = _check_pixel_single(url)
    pixel_value = result.has_pixel  # True/False/None
    error = result.error if result.has_pixel is None else None

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE company_enrichment
        SET Has_Google_Ads_Pixel = ?,
            Last_Error = ?,
            Last_Enriched_Date = date('now')
        WHERE CIN = ?
    """, (pixel_value, error, cin))
    conn.commit()
    conn.close()
    return result


def check_places_leads_batch(cins: list[str] = None,
                             min_quality: int = None,
                             max_workers: int = 10,
                             only_unchecked: bool = True) -> dict:
    """
    Run pixel check on a batch of Places leads.
    
    Args:
        cins: specific CINs to check (overrides filtering)
        min_quality: quality threshold (default from PIXEL_CHECK_MIN_QUALITY env)
        max_workers: parallel workers
        only_unchecked: if True, skip leads already checked

    Returns: dict with counts.
    """
    threshold = min_quality if min_quality is not None else PIXEL_CHECK_MIN_QUALITY

    conn = get_conn()
    cursor = conn.cursor()

    if cins:
        # Specific CINs — fetch their websites
        placeholders = ",".join(["?"] * len(cins))
        cursor.execute(f"""
            SELECT e.CIN, e.Website_URL
            FROM company_enrichment e
            WHERE e.CIN IN ({placeholders})
              AND e.Website_URL IS NOT NULL
        """, cins)
    else:
        # Batch by quality threshold
        unchecked_clause = "AND e.Has_Google_Ads_Pixel IS NULL" if only_unchecked else ""
        cursor.execute(f"""
            SELECT e.CIN, e.Website_URL
            FROM company_enrichment e
            JOIN places_leads p ON e.CIN = p.CIN
            WHERE e.Website_URL IS NOT NULL
              AND p.Quality_Score >= ?
              {unchecked_clause}
        """, (threshold,))

    targets = cursor.fetchall()
    conn.close()

    if not targets:
        return {"total": 0, "found": 0, "not_found": 0, "failed": 0}

    cin_map = {row["Website_URL"]: row["CIN"] for row in targets}
    urls = list(cin_map.keys())

    found = not_found = failed = 0

    # Use ThreadPoolExecutor for I/O-bound work
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(_check_pixel_single, url): url for url in urls}

        # Open one connection for all writes (faster than per-result)
        conn = get_conn()
        cursor = conn.cursor()

        try:
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                cin = cin_map[url]
                result: PixelResult = future.result()
                pixel_value = result.has_pixel
                error = result.error if result.has_pixel is None else None

                cursor.execute("""
                    UPDATE company_enrichment
                    SET Has_Google_Ads_Pixel = ?,
                        Last_Error = ?,
                        Last_Enriched_Date = date('now')
                    WHERE CIN = ?
                """, (pixel_value, error, cin))

                if result.has_pixel is True:
                    found += 1
                elif result.has_pixel is False:
                    not_found += 1
                else:
                    failed += 1

            conn.commit()
        finally:
            conn.close()

    return {
        "total": len(targets),
        "found": found,
        "not_found": not_found,
        "failed": failed,
    }