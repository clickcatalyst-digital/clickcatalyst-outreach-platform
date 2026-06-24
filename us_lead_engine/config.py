# us_lead_engine/config.py
# Single source of truth for the ICP query, field selection, and provider costs.

import os
from dotenv import load_dotenv

load_dotenv()  # load .env so env vars are available to ALL us_lead_engine modules

# ---------------------------------------------------------------------------
# ICP — the search query (concern #3: precise POC from the first request)
# Validated live: this exact filter returned 741 US agency founders/owners
# with verified emails, 0 credits spent.
# ---------------------------------------------------------------------------

ICP_QUERY = {
    "person_titles": ["Founder", "Owner", "CEO", "Managing Director", "Co-Founder"],
    "person_seniorities": ["owner", "founder", "c_suite"],
    "organization_num_employees_ranges": ["11,50", "51,200"],   # small + medium
    "person_locations": ["United States"],
    "q_organization_keyword_tags": ["digital marketing agency", "advertising agency"],
    "contact_email_status": ["verified"],   # only prospects with a revealable verified email
    # NOTE: tech-stack filtering is a PAID feature ("advanced filter" — 422 on free plan).
    # Uncomment on Basic+ to pre-filter ad-runners server-side and save reveal credits:
    # "currently_using_any_of_technology_uids": ["google_tag_manager"],
    "per_page": 25,
}

# Minimum role_classifier score to qualify a lead for an email reveal.
MIN_ROLE_SCORE = 75   # DECISION_MAKER (85-100) + strong MARKETING_LEADER (75+)

# Title ladder — when a company has multiple matches, prefer the highest here.
TITLE_PRIORITY = [
    "founder", "owner", "co-founder", "ceo", "managing director",
    "president", "head of marketing", "growth",
]

# ---------------------------------------------------------------------------
# FIELD SELECTION (concern #4: don't waste anything; keep only useful columns)
# These are the fields we persist from a search result. Everything else is dropped.
# ---------------------------------------------------------------------------

SEARCH_FIELDS = [
    "id", "first_name", "title",
    "organization.name", "organization.primary_domain",
    "organization.estimated_num_employees", "organization.industry",
    "city", "state", "country",
]

# Fields we expect back from a 1-credit enrich (the payoff columns).
ENRICH_FIELDS = ["email", "last_name", "linkedin_url", "organization.website_url"]

# ---------------------------------------------------------------------------
# PROVIDER COST TABLE (concern #2: cost calculator)
# All Apollo plans work out to ~$0.02 per revealed email.
# ---------------------------------------------------------------------------

# Which plan we're currently on — drives $ math in cost_tracker.
CURRENT_PLAN = os.getenv("APOLLO_PLAN", "free")

APOLLO_PLANS = {
    #              credits/yr   $/seat/mo   credits/mo (approx)
    "free":         {"credits_year": 1200,  "usd_month": 0,   "credits_month": 100},
    "basic":        {"credits_year": 30000, "usd_month": 49,  "credits_month": 2500},
    "professional": {"credits_year": 48000, "usd_month": 79,  "credits_month": 4000},
    "organization": {"credits_year": 72000, "usd_month": 119, "credits_month": 6000},
}


def usd_per_credit(plan: str = None) -> float:
    """Effective $ cost of one reveal credit on the given plan."""
    p = APOLLO_PLANS[plan or CURRENT_PLAN]
    if p["credits_year"] == 0 or p["usd_month"] == 0:
        return 0.0
    return round((p["usd_month"] * 12) / p["credits_year"], 4)


# ---------------------------------------------------------------------------
# DB / API
# ---------------------------------------------------------------------------

DB_PATH = os.path.join(os.path.dirname(__file__), "us_leads.db")
# Main ClickCatalyst pipeline DB — the export target (same default as api/database.py).
MAIN_DB_PATH = os.getenv(
    "DB_PATH",
    "/Users/pujan/Developer/data_collector/indian_companies/company_master_data.db",
)
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")
APOLLO_BASE = "https://api.apollo.io/api/v1"   # NOTE: /api/v1, not /v1 (the /v1 base is deprecated)

# Quality gate before we spend a reveal credit.
MIN_EMPLOYEES = 11
MAX_EMPLOYEES = 200
QUALIFY_REQUIRES_PIXEL = True   # only reveal emails for companies running Google Ads
