# api/services/lead_quality.py
# Quality scoring and phone normalization for Places leads.

import re
import json

# --- Quality scoring -----------------------------------------------------

POSITIVE_KEYWORDS = [
    "ppc", "google ads", "performance marketing", "paid media",
    "digital marketing", "sem", "search marketing", "growth marketing",
]

NEGATIVE_KEYWORDS_HARD = [
    "outdoor", "ooh", "billboard", "hoarding", "print",
    "newspaper", "radio", "tv ads",
]

NEGATIVE_KEYWORDS_SOFT = [
    "branding", "logo design", "packaging", "video production",
    "photography", "event management", "interior",
]


def score_lead(name: str | None, primary_type: str | None,
               types_json: str | None, user_rating_count: int | None) -> tuple[int, str]:
    """
    Returns (score 0-100, reasons CSV).
    Default threshold for "good lead" = 40.
    """
    score = 50  # neutral baseline
    reasons = []

    name_lower = (name or "").lower()
    types_list = []
    if types_json:
        try:
            types_list = [t.lower() for t in json.loads(types_json)]
        except (ValueError, TypeError):
            pass

    # Type-based signals
    if primary_type == "marketing_consultant":
        score += 30
        reasons.append("+30 marketing_consultant")
    elif "marketing_consultant" in types_list:
        score += 15
        reasons.append("+15 marketing_consultant in types")

    # Name-based positive signals
    matched_pos = [kw for kw in POSITIVE_KEYWORDS if kw in name_lower]
    if matched_pos:
        score += 20
        reasons.append(f"+20 name has {matched_pos[0]}")

    # Name-based negative signals (hard - clear category mismatch)
    matched_hard_neg = [kw for kw in NEGATIVE_KEYWORDS_HARD if kw in name_lower]
    if matched_hard_neg:
        score -= 40
        reasons.append(f"-40 OOH signal: {matched_hard_neg[0]}")

    # Name-based negative signals (soft - probably not PPC focus)
    matched_soft_neg = [kw for kw in NEGATIVE_KEYWORDS_SOFT if kw in name_lower]
    if matched_soft_neg:
        score -= 25
        reasons.append(f"-25 non-PPC service: {matched_soft_neg[0]}")

    # Maturity signal (helps real businesses outrank thin listings)
    if user_rating_count and user_rating_count >= 50:
        score += 10
        reasons.append("+10 established (50+ reviews)")
    elif user_rating_count and user_rating_count >= 200:
        score += 15  # this branch unreachable due to ordering above; intentional cap
        reasons.append("+15 well-established (200+ reviews)")

    # Clamp 0-100
    score = max(0, min(100, score))
    return score, ", ".join(reasons)


# --- Phone formatting ----------------------------------------------------

def format_phone(raw: str | None) -> str | None:
    """
    Normalize Indian phone number to XXX-XXX-XXXX format.
    Handles: '+91 92287 43563', '092287 43563', '079 4005 8027', etc.
    Returns None if input is unparseable.
    """
    if not raw:
        return None

    # Strip everything except digits
    digits = re.sub(r"\D", "", raw)

    # Remove India country code if present
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    # Remove leading 0 (trunk prefix)
    if digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]

    # 10-digit mobile or landline -> XXX-XXX-XXXX
    if len(digits) == 10:
        return f"{digits[0:3]}-{digits[3:6]}-{digits[6:10]}"

    # Fallback: return digit-grouped best-effort
    if len(digits) == 11:  # 0XX-XXX-XXXXX style landline that escaped trim
        return f"{digits[0:3]}-{digits[3:6]}-{digits[6:11]}"

    # Unparseable, return raw stripped of weird chars
    return raw.strip() or None