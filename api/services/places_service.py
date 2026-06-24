# api/services/places_service.py
# Google Places API (New) client - Text Search endpoint

import os
import requests
from typing import Optional

PLACES_BASE = "https://places.googleapis.com/v1"

# Field mask: only these fields are requested + billed
# Tier 1 + Tier 2 + geo + maps_uri per design decision
FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.nationalPhoneNumber",
    "places.internationalPhoneNumber",
    "places.websiteUri",
    "places.rating",
    "places.userRatingCount",
    "places.businessStatus",
    "places.primaryType",
    "places.types",
    "places.location",
    "places.googleMapsUri",
    "nextPageToken",
])


def search_text(
    query: str,
    location_bias: Optional[dict] = None,  # {"lat": float, "lng": float, "radius_m": int}
    page_token: Optional[str] = None,
    max_results: int = 20,
) -> dict:
    """
    Run a Google Places Text Search.
    Returns: {"places": [...], "next_page_token": str | None}
    Raises: requests.HTTPError on non-2xx response.
    """
    api_key = os.getenv("GOOGLE_PLACES_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_PLACES_API_KEY not set in environment")

    body = {
        "textQuery": query,
        "maxResultCount": min(max_results, 20),  # Google hard cap is 20/page
    }

    if page_token:
        body["pageToken"] = page_token

    if location_bias:
        body["locationBias"] = {
            "circle": {
                "center": {
                    "latitude": location_bias["lat"],
                    "longitude": location_bias["lng"],
                },
                "radius": location_bias.get("radius_m", 50000),
            }
        }

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }

    resp = requests.post(
        f"{PLACES_BASE}/places:searchText",
        json=body,
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    return {
        "places": data.get("places", []),
        "next_page_token": data.get("nextPageToken"),
    }


def normalize_place(place: dict) -> dict:
    """
    Convert raw Google Places response into our flat schema.
    Returns dict matching places_leads columns + synthetic CIN + quality + formatted phone.
    """
    from .lead_quality import score_lead, format_phone

    place_id = place.get("id")
    if not place_id:
        return None

    location = place.get("location") or {}
    display_name = (place.get("displayName") or {}).get("text")
    types = place.get("types") or []
    types_json = __import__("json").dumps(types)
    primary_type = place.get("primaryType")
    user_rating_count = place.get("userRatingCount")
    national_phone = place.get("nationalPhoneNumber")
    international_phone = place.get("internationalPhoneNumber")

    # Compute quality + formatted phone
    quality_score, quality_reasons = score_lead(
        display_name, primary_type, types_json, user_rating_count
    )
    phone_formatted = format_phone(national_phone or international_phone)

    return {
        "place_id": place_id,
        "cin": f"PLACES_{place_id}",
        "display_name": display_name,
        "formatted_address": place.get("formattedAddress"),
        "national_phone": national_phone,
        "international_phone": international_phone,
        "phone_formatted": phone_formatted,
        "website_uri": place.get("websiteUri"),
        "rating": place.get("rating"),
        "user_rating_count": user_rating_count,
        "business_status": place.get("businessStatus"),
        "primary_type": primary_type,
        "types_json": types_json,
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),
        "google_maps_uri": place.get("googleMapsUri"),
        "quality_score": quality_score,
        "quality_reasons": quality_reasons,
    }


# v2 TODO: Fuzzy MCA resolver
# ---------------------------
# When ready, build api/services/cin_resolver.py with this contract:
#
#   def resolve_cin(display_name: str, state_code: str | None) -> str | None
#
# Implementation outline:
#   1. Normalize place name: strip "PRIVATE LIMITED", "PVT LTD", "LLP", punctuation, lowercase
#   2. Filter company_data by state_code (extract from formatted_address)
#   3. Use rapidfuzz.process.extractOne against CompanyName with score_cutoff=85
#   4. Return matched CIN, or None
#
# Then run a background job that scans places_leads WHERE CIN_Resolution_Status = 'synthetic'
# and updates both places_leads.CIN and company_enrichment.CIN to the real value,
# carrying over Phone/Website_URL/etc.