# pixel_checker_02.py
# The Pixel Checker
# Input:  company_enrichment rows where Website_URL IS NOT NULL and Has_Google_Ads_Pixel IS NULL
# Action: Scans HTML + GTM container JSON for Google Ads signals
# Output: Updates Has_Google_Ads_Pixel (TRUE / FALSE / NULL on failure) in company_enrichment

import sqlite3
import requests
import re
import concurrent.futures
from dataclasses import dataclass
from typing import Optional

DB_PATH = '/Users/pujan/Developer/data_collector/indian_companies/company_master_data.db'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# Strict regex — avoids "draw-", "award-" false positives from plain 'aw-' substring match
AW_ID_PATTERN     = re.compile(r'\bAW-[0-9]{7,}\b', re.IGNORECASE)
GTM_ID_PATTERN    = re.compile(r'GTM-[A-Z0-9]{4,}', re.IGNORECASE)

# Signals inside a GTM container JSON that confirm Google Ads is active
GTM_ADS_SIGNALS   = ['awct', 'googtag', 'google_ads', 'aw-conversion', 'adwords']


# ---------------------------------------------------------------------------
# RESULT CONTAINER
# ---------------------------------------------------------------------------

@dataclass
class PixelResult:
    url: str
    has_pixel: Optional[bool]   # True / False / None (unreachable)
    method: Optional[str]       # How it was detected
    error: Optional[str]        # Failure reason if None


# ---------------------------------------------------------------------------
# STEP 1: Fetch HTML with redirect handling
# ---------------------------------------------------------------------------

def fetch_html(url: str, timeout: int = 10) -> Optional[requests.Response]:
    """Fetches URL, follows redirects, normalises http → https."""
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        return response if response.status_code == 200 else None
    except requests.exceptions.RequestException:
        # Try http fallback if https fails
        try:
            if url.startswith('https://'):
                response = requests.get(url.replace('https://', 'http://'), headers=HEADERS, timeout=timeout, allow_redirects=True)
                return response if response.status_code == 200 else None
        except requests.exceptions.RequestException:
            return None


# ---------------------------------------------------------------------------
# STEP 2: Scan static HTML for Google Ads signals
# ---------------------------------------------------------------------------

def scan_html_for_ads(html: str) -> tuple[bool, Optional[str]]:
    """
    Checks HTML for Google Ads signals. Returns (found: bool, method: str | None).
    Checks <head> first (fast path), then full HTML only if needed.
    """
    # Fast path: only scan <head> first
    head_end = html.find('</head>')
    head_html = html[:head_end].lower() if head_end != -1 else html[:3000].lower()

    if 'googletagmanager.com/gtag/js' in head_html:
        return True, "gtag.js in <head>"

    if AW_ID_PATTERN.search(head_html):
        return True, "AW- conversion ID in <head>"

    # Slower path: scan full HTML
    full_html = html.lower()

    if 'googletagmanager.com/gtag/js' in full_html:
        return True, "gtag.js in body"

    if AW_ID_PATTERN.search(full_html):
        return True, "AW- conversion ID in body"

    return False, None


# ---------------------------------------------------------------------------
# STEP 3: Fetch GTM container and scan for Google Ads tags inside it
# ---------------------------------------------------------------------------

def scan_gtm_container(html: str) -> tuple[bool, Optional[str]]:
    """
    Extracts GTM container ID from HTML, fetches the container JS,
    and scans it for Google Ads tag signals.
    """
    gtm_ids = GTM_ID_PATTERN.findall(html)
    if not gtm_ids:
        return False, None

    # Deduplicate — a page can have multiple GTM containers
    for gtm_id in set(gtm_ids):
        container_url = f"https://www.googletagmanager.com/gtm.js?id={gtm_id}"
        try:
            resp = requests.get(container_url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                continue

            container_text = resp.text.lower()

            for signal in GTM_ADS_SIGNALS:
                if signal in container_text:
                    return True, f"Google Ads tag '{signal}' found inside GTM container {gtm_id}"

        except requests.exceptions.RequestException:
            continue

    return False, None


# ---------------------------------------------------------------------------
# MASTER PIXEL CHECK (single URL)
# ---------------------------------------------------------------------------

def check_pixel(url: str) -> PixelResult:
    """
    Full pipeline for one URL:
      1. Fetch HTML
      2. Scan static HTML
      3. If GTM found, fetch container and scan it
    Returns PixelResult with has_pixel=None on any connection failure.
    """
    response = fetch_html(url)

    if response is None:
        return PixelResult(url=url, has_pixel=None, method=None, error="Unreachable / Non-200")

    html = response.text

    # Step 2: Static HTML scan
    found, method = scan_html_for_ads(html)
    if found:
        return PixelResult(url=url, has_pixel=True, method=method, error=None)

    # Step 3: GTM container deep scan
    found, method = scan_gtm_container(html)
    if found:
        return PixelResult(url=url, has_pixel=True, method=method, error=None)

    return PixelResult(url=url, has_pixel=False, method="Full scan — no signals found", error=None)


# ---------------------------------------------------------------------------
# BATCH RUNNER
# ---------------------------------------------------------------------------

def run_pixel_batch(max_workers: int = 10, batch_size: int = 50):
    """
    Pulls all enriched leads with pixel status unknown,
    runs multithreaded pixel checks, writes results back to SQLite.
    """
    print("🚀 INITIALIZING PIXEL CHECKER PIPELINE 🚀\n")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT CIN, Website_URL
        FROM company_enrichment
        WHERE Website_URL IS NOT NULL
        AND Has_Google_Ads_Pixel IS NULL
        AND (Unsubscribed IS NULL OR Unsubscribed = 0)
        LIMIT ?
    """, (batch_size,))
    targets = cursor.fetchall()

    if not targets:
        print("No leads pending pixel check. All caught up!")
        conn.close()
        return

    print(f"Loaded {len(targets)} companies for pixel scanning...\n")

    found_count  = 0
    failed_count = 0

    # Build a CIN lookup so we can write back after futures complete
    cin_map = {url: cin for cin, url in targets}
    urls    = list(cin_map.keys())

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(check_pixel, url): url for url in urls}

        for future in concurrent.futures.as_completed(future_to_url):
            url    = future_to_url[future]
            cin    = cin_map[url]
            result: PixelResult = future.result()

            # has_pixel is True/False/None — None stays NULL in SQLite
            pixel_value = result.has_pixel  # Python None → SQLite NULL automatically

            if result.has_pixel is True:
                print(f"✅ ADS FOUND  | {url} | via: {result.method}")
                found_count += 1
            elif result.has_pixel is False:
                print(f"❌ NO ADS     | {url}")
            else:
                print(f"⚠️  UNREACHABLE | {url} | {result.error} — will retry next run")
                failed_count += 1

            cursor.execute("""
                UPDATE company_enrichment
                SET Has_Google_Ads_Pixel = ?
                WHERE CIN = ?
            """, (pixel_value, cin))
            conn.commit()

    conn.close()
    print("\n" + "=" * 60)
    print(f"🏁 PIXEL SCAN COMPLETE")
    print(f"   ✅ Ads Found:   {found_count}")
    print(f"   ❌ No Ads:      {len(targets) - found_count - failed_count}")
    print(f"   ⚠️  Unreachable: {failed_count} (NULL — will retry next run)")


# --- Execute ---
# run_pixel_batch()