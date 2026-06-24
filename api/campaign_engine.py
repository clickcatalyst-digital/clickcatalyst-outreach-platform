# api/campaign_engine.py
# Decides which campaign variant to assign to a lead
# based on NIC code, segment, company profile
# Returns a campaign config dict consumed by email_engine_04

NIC_ECOMM   = {'47910'}
NIC_SOFTWARE = {'62000'}
NIC_AGENCY  = {'73100', '73200', '73101', '73210'}
NIC_CONSULT = {'70200'}


def get_campaign_variant(lead: dict) -> str:
    """
    Takes a lead dict with at minimum:
      - nic_code
      - ICP_Segment
      - Competitor_Count (optional)
      - Has_GMB (optional)

    Returns a variant_key string that maps to campaign_templates.Variant_Key
    """
    nic       = str(lead.get('nic_code') or '').strip()
    count     = int(lead.get('Competitor_Count') or 0)
    has_gmb   = bool(lead.get('Has_GMB'))

    # --- Tier 1: E-commerce ---
    if nic in NIC_ECOMM:
        if count >= 10:
            return 'ecomm_pmax_competitive_v1'   # many competitors → fear angle
        elif has_gmb:
            return 'ecomm_pmax_gmb_v1'           # has GMB → local dominance angle
        else:
            return 'ecomm_pmax_v1'               # standard e-comm audit

    # --- Tier 1: Software / SaaS ---
    if nic in NIC_SOFTWARE:
        if count >= 10:
            return 'saas_funnel_competitive_v1'
        else:
            return 'saas_funnel_v1'              # funnel leakage angle

    # --- Tier 2: Agency ---
    if nic in NIC_AGENCY:
        return 'agency_whitelabel_v1'            # white-label SaaS pitch

    # --- Tier 3: Consulting ---
    if nic in NIC_CONSULT:
        return 'consulting_generic_v1'

    # --- Fallback ---
    return 'generic_audit_v1'


def get_ab_variant(cin: str, variant_key: str) -> str:
    """
    Simple deterministic A/B split based on CIN hash.
    Returns variant_key + '_a' or '_b' — no randomness,
    same CIN always gets same variant for consistency.
    """
    bucket = sum(ord(c) for c in cin) % 2
    return f"{variant_key}_a" if bucket == 0 else f"{variant_key}_b"


# ---------------------------------------------------------------------------
# DEFAULT SEED TEMPLATES
# Called once on startup to populate campaign_templates if empty
# ---------------------------------------------------------------------------

DEFAULT_TEMPLATES = [
    {
        "Variant_Key":  "ecomm_pmax_v1_a",
        "Segment":      "Tier 1 - E-commerce",
        "Subject_Line": "Your Google Shopping campaigns are leaking — here's proof",
        "Body_HTML":    """<p>Hi,</p>
<p>I was auditing Google Ads activity in the e-commerce space and came across <strong>{company_name}</strong>.</p>
<p>{personalized_sentence}</p>
<p>I ran a quick Performance Max audit on your account structure and found several budget inefficiencies worth flagging. <a href="{audit_url}">View the full leak report here</a>.</p>
<p>Happy to walk you through it.<br/>Pujan<br/><span style="color:#999;font-size:12px;">ClickCatalyst · clickcatalyst.digital</span></p>""",
        "Body_Plain":   "Hi,\n\nI was auditing Google Ads activity in the e-commerce space and came across {company_name}.\n\n{personalized_sentence}\n\nI ran a quick Performance Max audit and found several budget inefficiencies. View the full report: {audit_url}\n\nHappy to walk you through it.\nPujan\nClickCatalyst · clickcatalyst.digital",
        "CTA_URL":      "https://clickcatalyst.digital/free-audit",
    },
    {
        "Variant_Key":  "ecomm_pmax_v1_b",
        "Segment":      "Tier 1 - E-commerce",
        "Subject_Line": "Quick question about your Google Ads spend",
        "Body_HTML":    """<p>Hi,</p>
<p>I noticed <strong>{company_name}</strong> is active in a competitive segment.</p>
<p>{personalized_sentence}</p>
<p>I put together a short audit of where budget is likely leaking in your campaigns. <a href="{audit_url}">See the findings here</a>.</p>
<p>Pujan<br/><span style="color:#999;font-size:12px;">ClickCatalyst · clickcatalyst.digital</span></p>""",
        "Body_Plain":   "Hi,\n\nI noticed {company_name} is active in a competitive segment.\n\n{personalized_sentence}\n\nI put together a short audit of where budget is likely leaking. See findings: {audit_url}\n\nPujan\nClickCatalyst · clickcatalyst.digital",
        "CTA_URL":      "https://clickcatalyst.digital/free-audit",
    },
    {
        "Variant_Key":  "ecomm_pmax_competitive_v1_a",
        "Segment":      "Tier 1 - E-commerce (High Competition)",
        "Subject_Line": "Your competitors are outbidding you — I checked",
        "Body_HTML":    """<p>Hi,</p>
<p><strong>{company_name}</strong> is operating in a dense competitive bracket.</p>
<p>{personalized_sentence}</p>
<p>The brands winning impression share in your bracket are doing one thing differently in their PMax campaigns. <a href="{audit_url}">Here's what I found</a>.</p>
<p>Pujan<br/><span style="color:#999;font-size:12px;">ClickCatalyst · clickcatalyst.digital</span></p>""",
        "Body_Plain":   "Hi,\n\n{company_name} is operating in a dense competitive bracket.\n\n{personalized_sentence}\n\nThe brands winning impression share are doing one thing differently. Here's what I found: {audit_url}\n\nPujan\nClickCatalyst",
        "CTA_URL":      "https://clickcatalyst.digital/free-audit",
    },
    {
        "Variant_Key":  "ecomm_pmax_competitive_v1_b",
        "Segment":      "Tier 1 - E-commerce (High Competition)",
        "Subject_Line": "{competitor_count} companies are competing for your exact customers",
        "Body_HTML":    """<p>Hi,</p>
<p>I mapped the Google Ads landscape around <strong>{company_name}</strong>.</p>
<p>{personalized_sentence}</p>
<p>I identified the exact budget and bidding gaps that are costing you impression share. <a href="{audit_url}">See the competitive audit</a>.</p>
<p>Pujan<br/><span style="color:#999;font-size:12px;">ClickCatalyst · clickcatalyst.digital</span></p>""",
        "Body_Plain":   "Hi,\n\nI mapped the Google Ads landscape around {company_name}.\n\n{personalized_sentence}\n\nSee the competitive audit: {audit_url}\n\nPujan\nClickCatalyst",
        "CTA_URL":      "https://clickcatalyst.digital/free-audit",
    },
    {
        "Variant_Key":  "saas_funnel_v1_a",
        "Segment":      "Tier 1 - Software / SaaS",
        "Subject_Line": "Your trial signups are leaking from Google Ads",
        "Body_HTML":    """<p>Hi,</p>
<p>I was reviewing Google Ads funnel data for software companies and came across <strong>{company_name}</strong>.</p>
<p>{personalized_sentence}</p>
<p>I identified specific drop-off points in your paid acquisition funnel. <a href="{audit_url}">View the funnel leakage report</a>.</p>
<p>Pujan<br/><span style="color:#999;font-size:12px;">ClickCatalyst · clickcatalyst.digital</span></p>""",
        "Body_Plain":   "Hi,\n\nI was reviewing Google Ads funnel data for software companies and came across {company_name}.\n\n{personalized_sentence}\n\nView the funnel leakage report: {audit_url}\n\nPujan\nClickCatalyst",
        "CTA_URL":      "https://clickcatalyst.digital/free-funnel-audit",
    },
    {
        "Variant_Key":  "saas_funnel_v1_b",
        "Segment":      "Tier 1 - Software / SaaS",
        "Subject_Line": "Are your Google Ads actually converting to paid users?",
        "Body_HTML":    """<p>Hi,</p>
<p>Quick question for <strong>{company_name}</strong> — are your Google Ads campaigns optimised for trial signups or just clicks?</p>
<p>{personalized_sentence}</p>
<p>I ran a funnel analysis and the findings are worth 5 minutes of your time. <a href="{audit_url}">See the report</a>.</p>
<p>Pujan<br/><span style="color:#999;font-size:12px;">ClickCatalyst · clickcatalyst.digital</span></p>""",
        "Body_Plain":   "Hi,\n\nQuick question for {company_name} — are your Google Ads optimised for trial signups or just clicks?\n\n{personalized_sentence}\n\nSee the report: {audit_url}\n\nPujan\nClickCatalyst",
        "CTA_URL":      "https://clickcatalyst.digital/free-funnel-audit",
    },
    {
        "Variant_Key":  "agency_whitelabel_v1_a",
        "Segment":      "Tier 2 - Agency",
        "Subject_Line": "White-label Google Ads diagnostics for your clients",
        "Body_HTML":    """<p>Hi,</p>
<p>I built a Google Ads diagnostic platform that agencies are using to deliver audits at scale — and I think it fits what <strong>{company_name}</strong> does.</p>
<p>It generates branded audit reports in minutes, not hours. <a href="{audit_url}">See a live demo</a>.</p>
<p>Happy to set up a quick call.<br/>Pujan<br/><span style="color:#999;font-size:12px;">ClickCatalyst · clickcatalyst.digital</span></p>""",
        "Body_Plain":   "Hi,\n\nI built a Google Ads diagnostic platform that agencies use to deliver audits at scale — and I think it fits what {company_name} does.\n\nIt generates branded audit reports in minutes. See a live demo: {audit_url}\n\nHappy to set up a quick call.\nPujan\nClickCatalyst",
        "CTA_URL":      "https://clickcatalyst.digital",
    },
    {
        "Variant_Key":  "agency_whitelabel_v1_b",
        "Segment":      "Tier 2 - Agency",
        "Subject_Line": "How are you currently auditing client Google Ads accounts?",
        "Body_HTML":    """<p>Hi,</p>
<p>Genuinely curious — how does <strong>{company_name}</strong> currently run Google Ads audits for clients?</p>
<p>I built ClickCatalyst specifically to automate this. It plugs into any Google Ads account and produces a full diagnostic in under 60 seconds. <a href="{audit_url}">Try it on a client account</a>.</p>
<p>Pujan<br/><span style="color:#999;font-size:12px;">ClickCatalyst · clickcatalyst.digital</span></p>""",
        "Body_Plain":   "Hi,\n\nGenuinely curious — how does {company_name} currently run Google Ads audits for clients?\n\nI built ClickCatalyst to automate this. Try it on a client account: {audit_url}\n\nPujan\nClickCatalyst",
        "CTA_URL":      "https://clickcatalyst.digital",
    },
    {
        "Variant_Key":  "generic_audit_v1_a",
        "Segment":      "Generic",
        "Subject_Line": "Found some Google Ads inefficiencies for {company_name}",
        "Body_HTML":    """<p>Hi,</p>
<p>I came across <strong>{company_name}</strong> while reviewing Google Ads activity in your sector.</p>
<p>{personalized_sentence}</p>
<p>I ran a quick diagnostic and found a few things worth flagging. <a href="{audit_url}">See the audit report</a>.</p>
<p>Pujan<br/><span style="color:#999;font-size:12px;">ClickCatalyst · clickcatalyst.digital</span></p>""",
        "Body_Plain":   "Hi,\n\nI came across {company_name} while reviewing Google Ads activity in your sector.\n\n{personalized_sentence}\n\nSee the audit report: {audit_url}\n\nPujan\nClickCatalyst",
        "CTA_URL":      "https://clickcatalyst.digital/free-audit",
    },
    {
        "Variant_Key":  "generic_audit_v1_b",
        "Segment":      "Generic",
        "Subject_Line": "Your Google Ads spend — a quick observation",
        "Body_HTML":    """<p>Hi,</p>
<p>I ran a brief audit on <strong>{company_name}</strong>'s Google Ads footprint and noticed a few patterns.</p>
<p>{personalized_sentence}</p>
<p><a href="{audit_url}">Here's what I found</a> — no strings attached.</p>
<p>Pujan<br/><span style="color:#999;font-size:12px;">ClickCatalyst · clickcatalyst.digital</span></p>""",
        "Body_Plain":   "Hi,\n\nI ran a brief audit on {company_name}'s Google Ads footprint and noticed a few patterns.\n\n{personalized_sentence}\n\nHere's what I found: {audit_url}\n\nPujan\nClickCatalyst",
        "CTA_URL":      "https://clickcatalyst.digital/free-audit",
    },
]


def seed_default_templates(conn):
    """Inserts default templates if campaign_templates is empty."""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM campaign_templates")
    if cursor.fetchone()[0] > 0:
        return
    for t in DEFAULT_TEMPLATES:
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO campaign_templates
                    (Variant_Key, Segment, Subject_Line, Body_HTML, Body_Plain, CTA_URL)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (t['Variant_Key'], t['Segment'], t['Subject_Line'],
                  t['Body_HTML'], t['Body_Plain'], t['CTA_URL']))
        except Exception:
            pass
    conn.commit()