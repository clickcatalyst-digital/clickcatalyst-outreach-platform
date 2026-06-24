# domain_extractor_01.py
# The Domain & Entity Extractor

import sqlite3
import requests
import re
from urllib.parse import urlparse
from difflib import SequenceMatcher
import os
from dotenv import load_dotenv
import json
import time
from bs4 import BeautifulSoup
import urllib.parse

load_dotenv()

# --- CONFIGURATION ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API")
DB_PATH = '/Users/pujan/Developer/data_collector/indian_companies/company_master_data.db'

# --- THE MASTER B2B BLACKLIST ---
B2B_BLACKLIST = [
    'zaubacorp', 'tofler', 'indiamart', 'justdial', 'dubleu', 'falconebiz',
    'linkedin', 'facebook', 'instagram', 'thecompanycheck', 'economictimes',
    'instafinancials', 'ambitionbox', 'quickcompany', 'tradeindia', 'masterdata',
    'zoominfo', 'glassdoor', 'owler', 'tracxn', 'crunchbase', 'pitchbook',
    'dir.indiamart', 'fundoodata', 'connect2india', 'vakilsearch', 'cleartax',
    'startupindia', 'easytoca', 'companydetails', '99corporates', 'fincrif',
    'planetexim', 'mastersindia', 'corpdir', 'blogspot', 'wordpress', 'indiafilings',
    'wikipedia.org', 'gov.in', 'nic.in', 'serviceonline', 'nemetschek'
]

NON_COMMERCIAL_SUFFIXES = ('.gov.in', '.gov', '.edu', '.edu.in', '.nic.in', 'karnataka.gov.in')

# --- THE AD-SPEND PIVOT DICTIONARY ---
PARENT_TO_CHILD_DOMAIN = {
    "bundl.com": "swiggy.com",
    "one97.com": "paytm.com",
    "oravel.com": "oyorooms.com",
    "apiholdings.in": "pharmeasy.in",
    "brainbees.com": "firstcry.com",
    "fsnecommerce.com": "nykaa.com",
    "innovativeretail.in": "bigbasket.com",
    "fashnear.com": "meesho.com",
    "grofers.com": "blinkit.com",
    "zomato.com": "zomato.com",
    "resilientinnovations.com": "bharatpe.com",
    "defmacro.in": "cleartax.in",
    "nextbillion.in": "groww.in",
    "dreamplug.com": "cred.club",
    "razorpay.com": "razorpay.com",
    "anitechnologies.com": "olacabs.com",
    "roppen.in": "rapido.bike",
    "urbanclap.com": "urbancompany.com",
    "girnarsoft.com": "cardekho.com",
    "thinkandlearn.in": "byjus.com",
    "sortinghat.in": "unacademy.com",
    "sporta.in": "dream11.com",
    "games24x7.com": "my11circle.com",
    "curefit.com": "cult.fit",
    "1mg.com": "tata1mg.com"
}


# ---------------------------------------------------------------------------
# SHARED UTILITIES
# ---------------------------------------------------------------------------

def clean_company_name(name):
    """Strips legal jargon to find the core brand name."""
    clean = re.sub(r'\b(PRIVATE LIMITED|LIMITED|LTD|OPC|LLP|INC|PVT)\b', '', name, flags=re.IGNORECASE)
    return re.sub(r'[^a-zA-Z0-9\s]', '', clean).strip()

def passes_bouncer_check(url, cleaned_name):
    """
    Acts as a bouncer to catch Google autocorrect hallucinations.
    Ensures the domain name actually resembles the company name.
    """
    try:
        # Extract just the core domain word (e.g., 'swiftinnovation' from 'www.swiftinnovation.com')
        netloc = urlparse(url).netloc.lower()
        core_domain = netloc.replace('www.', '').split('.')[0]
    except Exception:
        return False

    name_nospace = cleaned_name.lower().replace(" ", "")
    first_word = cleaned_name.lower().split()[0]

    # Check 1: Is the core domain inside the company name? (e.g., 'tata' inside 'tatamotors')
    if len(core_domain) > 3 and core_domain in name_nospace:
        return True

    # Check 2: Is the first main word of the company in the domain? (e.g., 'snyft' inside 'snyftinnovations')
    if len(first_word) >= 3 and first_word in core_domain:
        return True

    # Check 3: Do they share the same first 4 letters? (Catches weird abbreviations)
    # This specifically blocks 'Snyft' (snyf) from matching 'Swift' (swif)
    if len(core_domain) >= 4 and len(name_nospace) >= 4:
        if core_domain[:4] == name_nospace[:4]:
            return True

    # If it fails all 3, it's an autocorrect hallucination or a government portal.
    return False


def is_domain_related_to_company(domain_netloc, cleaned_name):
    """Returns True if the domain plausibly belongs to the company."""
    domain_word = domain_netloc.replace('www.', '').split('.')[0].lower()
    comp_words = cleaned_name.lower().split()
    word_match = any(word in domain_word or domain_word in word for word in comp_words if len(word) > 2)
    acronym = "".join([w[0] for w in comp_words if w])
    acronym_match = (domain_word == acronym) or (domain_word in acronym and len(domain_word) >= 2)
    return word_match or acronym_match


def is_candidate_url_valid(actual_url, cleaned_name):
    """
    Single-pass filter: blacklist → non-commercial → ghost company.
    Returns (is_valid: bool, root_url: str, reason: str | None)
    """
    parsed = urlparse(actual_url)
    domain = parsed.netloc.lower()
    root_url = f"{parsed.scheme}://{parsed.netloc}"

    # 2. Check Blacklist
    if any(bad_word in domain for bad_word in B2B_BLACKLIST):
        return False, root_url, f"Skipped Aggregator/Directory: {domain}"

    # 3. The Bouncer Check (Catch Autocorrects)
    if not passes_bouncer_check(actual_url, cleaned_name):
        return False, root_url, f"Bouncer Rejected: Domain '{domain}' does not match name '{cleaned_name}'"

    if domain.endswith(NON_COMMERCIAL_SUFFIXES):
        return False, root_url, f"[Skipped Non-Commercial]: {domain}"

    if not is_domain_related_to_company(parsed.netloc, cleaned_name):
        return False, root_url, f"[Skipped Ghost/Unrelated]: {root_url}"

    return True, root_url, None


def is_valid_b2b_domain(url):
    """Checks if a URL is a legitimate business domain and not a directory/social site."""
    if not url:
        return False
    domain = url.lower()
    if any(bad_word in domain for bad_word in B2B_BLACKLIST):
        return False
    if domain.endswith(NON_COMMERCIAL_SUFFIXES):
        return False
    return True


def upgrade_to_ad_domain(extracted_url):
    """Intercepts corporate domains and swaps them for ad-spending consumer domains."""
    if not extracted_url:
        return None
    base_domain = urlparse(extracted_url).netloc.replace('www.', '').lower()
    if base_domain in PARENT_TO_CHILD_DOMAIN:
        child_domain = PARENT_TO_CHILD_DOMAIN[base_domain]
        new_url = f"https://www.{child_domain}"
        print(f"🔄 SWAPPED: Corporate site '{base_domain}' upgraded to Ad Domain -> {new_url}")
        return new_url
    return extracted_url


# ---------------------------------------------------------------------------
# LAYER 1: Google Places (New API)
# ---------------------------------------------------------------------------

def test_google_places_new_api(company_name, state):
    print(f"--- Testing Places API (NEW) for: {company_name} ---")

    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.websiteUri,places.businessStatus"
    }

    cleaned_name = clean_company_name(company_name)
    payload = {"textQuery": f"{cleaned_name} {state}"}

    response = requests.post(url, json=payload, headers=headers, timeout=10)
    data = response.json()

    if not ("places" in data and len(data["places"]) > 0):
        print(f"❌ No GMB Profile Found or API Error: {data}")
        return False, None

    place = data["places"][0]
    gmb_name = place["displayName"]["text"]
    similarity = SequenceMatcher(
        None,
        cleaned_name.lower().replace(" ", ""),
        gmb_name.lower().replace(" ", "")
    ).ratio()

    print(f"✅ GMB Profile Found!")
    print(f"   Input Name:    {cleaned_name}")
    print(f"   GMB Reg. Name: {gmb_name}")
    print(f"   Match Score:   {similarity:.2f}")

    if similarity <= 0.4:
        print("\n⚠️ WARNING: Name match too low. Likely a false positive.")
        return False, None

    print("\n--- Verified GMB Details ---")
    print(f"Status:  {place.get('businessStatus', 'UNKNOWN')}")
    print(f"Address: {place.get('formattedAddress', 'None')}")

    website = place.get('websiteUri')
    print(f"Website: {website if website else 'Not listed on GMB.'}")

    return True, website


# ---------------------------------------------------------------------------
# LAYER 2: DuckDuckGo Fallback
# ---------------------------------------------------------------------------

def fallback_duckduckgo_search(company_name, state):
    print(f"--- Running Hardened DuckDuckGo Backup for: {company_name} ---")

    cleaned_name = clean_company_name(company_name)
    query = f"{cleaned_name} {state} official website"
    url = f"https://html.duckduckgo.com/html/?q={query}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            print("DDG blocked the request. Try again later.")
            return "BLOCKED"

        soup = BeautifulSoup(response.text, 'html.parser')

        for a_tag in soup.find_all('a', class_='result__snippet'):
            link = a_tag.get('href')
            if not link:
                continue

            parsed = urlparse(link)
            actual_url = parsed.query.split('uddg=')[1].split('&')[0] if 'uddg=' in parsed.query else link
            actual_url = urllib.parse.unquote(actual_url)

            if 'duckduckgo.com/y.js' in actual_url or 'ad_domain' in actual_url:
                print("   [Skipped Ad]: Sponsored Result")
                continue

            valid, root_url, reason = is_candidate_url_valid(actual_url, cleaned_name)
            if not valid:
                print(f"   {reason}")
                continue

            print(f"✅ Found Organic URL via DuckDuckGo: {root_url}")
            return root_url

        print("❌ No valid website found on DuckDuckGo after filtering.")
        return None

    except Exception as e:
        print(f"Scraper Error: {e}")
        return None


# ---------------------------------------------------------------------------
# LAYER 3: Serper.dev Fallback
# ---------------------------------------------------------------------------

def fallback_serper_search(company_name, state):
    print(f"--- 🚨 TRIGGERING LAYER 3: Serper.dev for {company_name} ---")

    cleaned_name = clean_company_name(company_name)
    query = f"{cleaned_name} {state} official website"
    url = "https://google.serper.dev/search"
    headers = {
        'X-API-KEY': SERPER_API_KEY,
        'Content-Type': 'application/json'
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps({"q": query}), timeout=10)
        data = response.json()

        if 'organic' not in data:
            print("❌ No organic results found on Google.")
            return None

        for result in data['organic']:
            actual_url = result.get('link')
            if not actual_url:
                continue

            valid, root_url, reason = is_candidate_url_valid(actual_url, cleaned_name)
            if not valid:
                print(f"   {reason}")
                continue

            print(f"✅ Found Organic URL via Serper: {root_url}")
            return root_url

        print("❌ No valid website found on Serper after filtering.")
        return None

    except Exception as e:
        print(f"Layer 3 API Error: {e}")
        return None


# ---------------------------------------------------------------------------
# MASTER ORCHESTRATOR
# ---------------------------------------------------------------------------

def master_domain_finder(company_name, state):
    """The 3-Layer Master Engine: Returns (URL, Source, Has_GMB)"""
    print(f"\n--- Processing: {company_name} ---")

    # --- LAYER 1: Google Places API ---
    try:
        gmb_success, website = test_google_places_new_api(company_name, state)
    except Exception as e:
        print(f"   [GMB Error]: {e}")
        gmb_success, website = False, None

    if gmb_success and website:
        if is_valid_b2b_domain(website):
            print(f"🎯 WIN (Layer 1 - GMB): {website}")
            return upgrade_to_ad_domain(website), "Layer 1 - GMB", True
        else:
            print(f"   [GMB Rejected]: {website} is a social/directory link.")

    # --- LAYER 2: DuckDuckGo Fallback ---
    print("⚠️ GMB Failed or no website. Triggering Layer 2 (DuckDuckGo)...")
    fallback_url = fallback_duckduckgo_search(company_name, state)
    source = "Layer 2 - DuckDuckGo"

    # --- LAYER 3: Serper.dev Fallback (SOS) ---
    if fallback_url in (None, "BLOCKED"):
        print("🚨 Layer 2 failed or found nothing. Triggering Layer 3 (Serper.dev)...")
        fallback_url = fallback_serper_search(company_name, state)
        source = "Layer 3 - Serper"

    # --- FINAL VERDICT & SWAP ---
    if fallback_url not in (None, "BLOCKED"):
        final_url = upgrade_to_ad_domain(fallback_url)
        print(f"🎯 WIN (Fallback): {final_url}")
        return final_url, source, False

    print("❌ FAILED: No valid B2B website found in any engine.")
    return None, "Failed / Not Found", False


# ---------------------------------------------------------------------------
# BATCH RUNNER
# ---------------------------------------------------------------------------

def run_enrichment_batch(batch_size=50):
    print("🚀 INITIALIZING ENRICHMENT PIPELINE 🚀\n")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT c.CIN, c.CompanyName, c.State
        FROM vw_qualified_leads c
        LEFT JOIN company_enrichment e ON c.CIN = e.CIN
        WHERE c.ICP_Segment = 'Tier 1: Brand - High Intent (Direct Buyers)'
        AND (e.Website_URL IS NULL OR e.Website_URL = '')
        AND (e.Enrichment_Attempts IS NULL OR e.Enrichment_Attempts < 5)
        AND (e.Unsubscribed IS NULL OR e.Unsubscribed = 0)
        LIMIT ?;
    """, (batch_size,))

    targets = cursor.fetchall()

    if not targets:
        print("No new Tier 1 leads found to enrich. Your pipeline is caught up!")
        conn.close()
        return

    print(f"Loaded {len(targets)} companies for processing. Starting the engine...\n")

    success_count = 0

    for cin, name, state in targets:
        print("=" * 60)

        website_url, domain_source, gmb_success = master_domain_finder(name, state)

        if website_url:
            cursor.execute('''
                INSERT INTO company_enrichment (CIN, Website_URL, Domain_Source, Has_GMB, Last_Enriched_Date, Pipeline_Status, Enrichment_Attempts, Last_Error)
                VALUES (?, ?, ?, ?, CURRENT_DATE, 'Enriched_Ready', 1, NULL)
                ON CONFLICT(CIN) DO UPDATE SET
                    Website_URL = ?,
                    Domain_Source = ?,
                    Has_GMB = ?,
                    Last_Enriched_Date = CURRENT_DATE,
                    Pipeline_Status = 'Enriched_Ready',
                    Enrichment_Attempts = COALESCE(Enrichment_Attempts, 0) + 1,
                    Last_Error = NULL
            ''', (cin, website_url, domain_source, gmb_success,
                  website_url, domain_source, gmb_success))
            success_count += 1
        else:
            cursor.execute('''
                INSERT INTO company_enrichment (CIN, Domain_Source, Last_Enriched_Date, Enrichment_Attempts, Last_Error)
                VALUES (?, ?, CURRENT_DATE, 1, ?)
                ON CONFLICT(CIN) DO UPDATE SET
                    Domain_Source = ?,
                    Last_Enriched_Date = CURRENT_DATE,
                    Enrichment_Attempts = COALESCE(Enrichment_Attempts, 0) + 1,
                    Last_Error = ?
            ''', (cin, domain_source, f"No website found via {domain_source}",
                  domain_source, f"No website found via {domain_source}"))

        conn.commit()
        time.sleep(2)

    conn.close()
    print("=" * 60)
    print(f"🏁 BATCH COMPLETE! Successfully found domains for {success_count} out of {len(targets)} companies.")


# --- Execute ---
# run_enrichment_batch()