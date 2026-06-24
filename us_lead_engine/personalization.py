# us_lead_engine/personalization.py
# Builds ONE observed, problem-first sentence per lead from signals we already
# capture at enrich. Rules-based (no LLM) — deterministic and cheap.
#
# Deliberately AVOIDS "you run Google Ads" (true of every agency = tautology).
# Leans on scale/size, which is a real, non-obvious operational pain.

def build_personalized_line(employee_count=None, city=None, industry=None):
    """
    Returns a single sentence to drop into {personalized_line}.
    Signals come from us_leads (Org_Employee_Count, City, Org_Industry).
    """
    size = employee_count or 0

    if size >= 50:
        return ("At your size, manually checking every client's Google Ads account for "
                "wasted spend each month isn't realistic to do well by hand.")
    if size >= 20:
        return ("Once you're managing this many client accounts, catching wasted spend "
                "in each one by hand gets hard to keep up with.")
    if size >= 11:
        return ("Past a handful of client accounts, spotting wasted spend in every Google "
                "Ads account manually starts to slip through the cracks.")
    # Fallback — still problem-first, no size claim.
    return ("Catching wasted spend across every client's Google Ads account by hand is "
            "tough to keep on top of.")
