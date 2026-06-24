# us_lead_engine/seed_campaigns.py
# Seeds the US agency cold-email arms into the main DB's campaign_templates table,
# so the existing Thompson sampler + A/B-promote + campaigns dashboard manage them.
#
# Strategy (locked 2026-06): problem-first ("Google can't audit its own waste"),
# ONE personalized line, free Efficiency & Waste audit on a client account,
# CTA = run the audit (NOT "send a code"), pre-launch (no proof claims),
# Founding Agency offer saved for the reply.
#
# Two arms test two openers:
#   _a  statement opener  ("Google can't audit its own waste")  + soft CTA
#   _b  question opener   ("how are you auditing for waste?")    + directive CTA
#
# Body is greeting → hook → {personalized_line} → offer/CTA → signature.
# The sender appends the CAN-SPAM footer + unsubscribe + open pixel.
#
# Run: python -m us_lead_engine.run_discovery --seed-campaigns  (UPSERTs — re-run to apply edits)

import sqlite3
from .config import MAIN_DB_PATH

BASE = "us_agency_waste_v1"

ARMS = [
    {
        "Variant_Key": f"{BASE}_a",
        "Segment": "US Agency - Waste",
        "Subject_Line": "Google can't audit its own waste",
        "Body_HTML": """<p>Hi {first_name},</p>
<p>Google can't really audit its own waste — it's incentivized to grow spend, not protect your clients' margins. So a lot of wasted spend just stays invisible in the standard interface.</p>
<p>{personalized_line}</p>
<p>I built a tool that surfaces it — wasted spend, tracking gaps, search-term bleed — and turns it into a white-label report you can hand straight to a client.</p>
<p>Worth running one against one of <strong>{company_name}</strong>'s client accounts to see what it finds?</p>
<p>Pujan<br/><span style="color:#6c757d;font-size:13px;">ClickCatalyst · clickcatalyst.digital</span></p>""",
        "Body_Plain": """Hi {first_name},

Google can't really audit its own waste — it's incentivized to grow spend, not protect your clients' margins. So a lot of wasted spend just stays invisible in the standard interface.

{personalized_line}

I built a tool that surfaces it — wasted spend, tracking gaps, search-term bleed — and turns it into a white-label report you can hand straight to a client.

Worth running one against one of {company_name}'s client accounts to see what it finds?

Pujan
ClickCatalyst · clickcatalyst.digital""",
        "CTA_URL": "https://clickcatalyst.digital/free-audit",
    },
    {
        "Variant_Key": f"{BASE}_b",
        "Segment": "US Agency - Waste",
        "Subject_Line": "how are you auditing client accounts for waste right now?",
        "Body_HTML": """<p>Hi {first_name},</p>
<p>Genuinely curious how <strong>{company_name}</strong> catches wasted spend across client Google Ads accounts today — most of it is invisible in Google's own interface, and Google isn't exactly motivated to flag it.</p>
<p>{personalized_line}</p>
<p>I built something that surfaces the waste and tracking issues automatically and turns it into a white-label report you can give a client.</p>
<p>Reply with "audit" and I'll run one on a client account.</p>
<p>Pujan<br/><span style="color:#6c757d;font-size:13px;">ClickCatalyst · clickcatalyst.digital</span></p>""",
        "Body_Plain": """Hi {first_name},

Genuinely curious how {company_name} catches wasted spend across client Google Ads accounts today — most of it is invisible in Google's own interface, and Google isn't exactly motivated to flag it.

{personalized_line}

I built something that surfaces the waste and tracking issues automatically and turns it into a white-label report you can give a client.

Reply with "audit" and I'll run one on a client account.

Pujan
ClickCatalyst · clickcatalyst.digital""",
        "CTA_URL": "https://clickcatalyst.digital/free-audit",
    },
]


def seed():
    conn = sqlite3.connect(MAIN_DB_PATH)
    cur = conn.cursor()
    inserted, updated = 0, 0
    for a in ARMS:
        cur.execute("SELECT 1 FROM campaign_templates WHERE Variant_Key = ?", (a["Variant_Key"],))
        if cur.fetchone():
            cur.execute("""
                UPDATE campaign_templates
                SET Segment = ?, Subject_Line = ?, Body_HTML = ?, Body_Plain = ?, CTA_URL = ?, Is_Active = 1
                WHERE Variant_Key = ?
            """, (a["Segment"], a["Subject_Line"], a["Body_HTML"], a["Body_Plain"],
                  a["CTA_URL"], a["Variant_Key"]))
            updated += 1
            print(f"   ~ updated {a['Variant_Key']}")
        else:
            cur.execute("""
                INSERT INTO campaign_templates
                    (Variant_Key, Segment, Subject_Line, Body_HTML, Body_Plain, CTA_URL, Is_Active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
            """, (a["Variant_Key"], a["Segment"], a["Subject_Line"],
                  a["Body_HTML"], a["Body_Plain"], a["CTA_URL"]))
            inserted += 1
            print(f"   + inserted {a['Variant_Key']}")
    conn.commit()
    conn.close()
    print(f"🏁 {inserted} inserted, {updated} updated.")


if __name__ == "__main__":
    seed()
