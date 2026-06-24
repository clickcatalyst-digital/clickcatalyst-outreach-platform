# us_lead_engine/role_classifier.py
# ICP role scoring. Rules-first, with Apollo's structured fields as the primary
# signal (seniority / departments) — no LLM needed at this stage.
#
# classify() returns (score 0-100, role_label, is_decision_maker).
# Use the score to rank within the accepted set, and the flag to auto-approve.

# --- Title keyword tiers (Tier 1 — used when Apollo fields are absent/ambiguous) ---

DECISION_MAKER = {           # owners / top execs — auto-approve
    "founder": 100, "co-founder": 100, "cofounder": 100, "owner": 95,
    "ceo": 95, "chief executive": 95, "president": 90, "managing director": 90,
    "managing partner": 90, "managing member": 88, "principal": 85, "partner": 85,
}

MARKETING_LEADER = {         # marketing decision influencers
    "cmo": 85, "chief marketing": 85, "vp marketing": 82, "vp of marketing": 82,
    "head of marketing": 80, "marketing director": 80, "director of marketing": 80,
    "head of growth": 78, "growth lead": 75, "demand generation": 75,
    "fractional cmo": 80,
}

MAYBE = {                    # weak — keep but low priority
    "marketing manager": 50, "growth": 45, "director": 45, "manager": 40,
}

REJECT_KEYWORDS = [          # clear non-ICP — score 0
    "designer", "developer", "engineer", "recruiter", "human resources", " hr ",
    "accountant", "assistant", "intern", "coordinator", "specialist", "analyst",
    "support", "bookkeeper", "receptionist", "student",
]

# Apollo structured seniority values that mean "decision maker".
APOLLO_DM_SENIORITIES = {"owner", "founder", "c_suite", "partner"}


def _title_score(title: str):
    t = f" {(title or '').lower()} "

    for kw in REJECT_KEYWORDS:
        if kw in t:
            return 0, "NOT_RELEVANT", False

    best, label = 0, "NOT_RELEVANT"
    for table, lbl in [(DECISION_MAKER, "DECISION_MAKER"),
                       (MARKETING_LEADER, "MARKETING_LEADER"),
                       (MAYBE, "MAYBE")]:
        for kw, score in table.items():
            if kw in t and score > best:
                best, label = score, lbl
    return best, label, best >= 85


def classify(title: str, seniority: str = None, departments=None):
    """
    Score a contact for PPC-agency outreach.

    Prefers Apollo's structured fields (free, pre-computed); falls back to
    title keyword rules. Returns (score, role_label, is_decision_maker).
    """
    departments = departments or []

    # Tier 0: trust Apollo's structured classification when it's a clear DM.
    if seniority and seniority.lower() in APOLLO_DM_SENIORITIES:
        # Still run the title rules to separate Founder (100) from Partner (85).
        t_score, t_label, _ = _title_score(title)
        score = max(t_score, 90)   # floor of 90 for a structured decision-maker
        label = t_label if t_label != "NOT_RELEVANT" else "DECISION_MAKER"
        return score, label, True

    if "c_suite" in departments:
        t_score, _, _ = _title_score(title)
        return max(t_score, 85), "DECISION_MAKER", True

    # Tier 1: title keyword rules.
    return _title_score(title)


if __name__ == "__main__":
    # Quick sanity check on the tricky titles the rules need to handle.
    samples = [
        ("Founder / CEO", "founder", ["c_suite"]),
        ("Senior Graphic Designer", None, []),
        ("Fractional CMO", None, []),
        ("Partner & Managing Director", "partner", []),
        ("Growth Strategist", None, []),
        ("Marketing Director", None, []),
    ]
    for title, sen, dep in samples:
        print(f"{classify(title, sen, dep)}  ←  {title!r}")
