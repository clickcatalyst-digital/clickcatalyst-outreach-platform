# us_lead_engine/run_discovery.py
# Entry point. Ties search -> qualify -> reveal -> export together.
#
#   --dry-run     search + qualify only, 0 credits (default)
#   --enrich N    reveal up to N qualified leads (N credits)
#   --cost        print spend report
#   --export      push qualified+revealed leads into the main pipeline
#
# Run: python -m us_lead_engine.run_discovery --dry-run

import argparse
import sqlite3

from .config import ICP_QUERY, MIN_ROLE_SCORE, MAIN_DB_PATH, QUALIFY_REQUIRES_PIXEL
from .db import get_conn
from . import apollo_client, cost_tracker, role_classifier


def _g(d, path):
    """Safe nested getter: _g(person, 'organization.name')."""
    cur = d
    for part in path.split("."):
        cur = (cur or {}).get(part) if isinstance(cur, dict) else None
    return cur


def upsert_lead(conn, p, source_query):
    """
    Insert a search result. The search endpoint only returns identity + has_*
    flags — domain, email, employee count, and location all come later at enrich.
    """
    conn.execute("""
        INSERT INTO us_leads
            (Apollo_Person_ID, First_Name, Title, Org_Name,
             Source_Query, Has_Email_Flag, Has_Direct_Phone, Pixel_Status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'unchecked')
        ON CONFLICT(Apollo_Person_ID) DO UPDATE SET
            Title = excluded.Title,
            Has_Email_Flag = excluded.Has_Email_Flag,
            Has_Direct_Phone = excluded.Has_Direct_Phone,
            Source_Query = excluded.Source_Query
    """, (
        p.get("id"), p.get("first_name"), p.get("title"),
        _g(p, "organization.name"),
        source_query,
        1 if p.get("has_email") else 0,
        p.get("has_direct_phone"),
    ))


def qualify(conn):
    """
    Free pre-reveal gate. The search constrained employee range and seniority
    server-side (tech filtering is paid, so NOT applied here) — so we score the
    title (role_classifier) and require a revealable email. Ad-running is confirmed
    post-reveal by the pixel check, once enrich gives us the domain.
    """
    cur = conn.cursor()
    cur.execute("SELECT ID, Title, Has_Email_Flag FROM us_leads")
    rows = cur.fetchall()

    qualified = 0
    for r in rows:
        score, label, _ = role_classifier.classify(r["Title"])
        ok = int(bool(r["Has_Email_Flag"]) and score >= MIN_ROLE_SCORE)
        conn.execute(
            "UPDATE us_leads SET Role_Score = ?, Role_Label = ?, Qualified = ? WHERE ID = ?",
            (score, label, ok, r["ID"]),
        )
        qualified += ok

    conn.commit()
    return qualified, len(rows)


def run_search(page=1):
    """Search the ICP, persist results, qualify. No credits spent. Returns # returned."""
    source_query = ", ".join(ICP_QUERY["person_titles"]) + " @ US agencies"
    people, total = apollo_client.search(ICP_QUERY, page=page)

    conn = get_conn()
    for p in people:
        upsert_lead(conn, p, source_query)
    conn.commit()

    qualified, scanned = qualify(conn)
    conn.close()

    print(f"🔎 Search page {page}: {len(people)} returned (of {total} total) — 0 credits")
    print(f"✅ Qualified: {qualified}/{scanned} passed the free gate")
    print(f"   Next: python -m us_lead_engine.run_discovery --enrich {min(qualified, 5)}")
    return len(people)


def _pixel_check(domain):
    """Run the existing root pixel checker on a revealed domain → yes/no/unreachable."""
    if not domain:
        return "unchecked"
    try:
        from pixel_checker_02 import check_pixel   # project-root module
    except ImportError:
        return "unchecked"
    try:
        res = check_pixel(domain)
    except Exception:
        return "unreachable"
    return {True: "yes", False: "no"}.get(res.has_pixel, "unreachable")


def run_enrich(n):
    """
    Reveal emails for up to N qualified, not-yet-enriched leads. Costs N credits.
    Highest role score first. Enrich also returns the domain + tech stack, so we
    run the precise pixel check here, before anything is exported.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT ID, Apollo_Person_ID, First_Name, Org_Name
        FROM us_leads
        WHERE Qualified = 1 AND Enriched_At IS NULL
        ORDER BY Role_Score DESC
        LIMIT ?
    """, (n,))
    targets = cur.fetchall()

    if not targets:
        print("   No qualified, unenriched leads. Run --dry-run first.")
        conn.close()
        return

    print(f"⚠️  About to spend up to {len(targets)} credit(s) revealing emails.")
    revealed = 0
    for t in targets:
        person = apollo_client.enrich(
            person_id=t["Apollo_Person_ID"],
            first_name=t["First_Name"],
            organization_name=t["Org_Name"],
        )
        if person:
            org = person.get("organization") or {}
            domain = org.get("primary_domain")
            pixel = _pixel_check(domain)
            conn.execute("""
                UPDATE us_leads SET
                    Email = ?, Last_Name = ?, Email_Status = ?, Email_Catchall = ?,
                    LinkedIn_URL = ?, Org_Domain = ?, Org_Employee_Count = ?,
                    Org_Industry = ?, City = ?, State = ?, Country = ?, Phone = ?,
                    Pixel_Status = ?, Enriched_At = CURRENT_TIMESTAMP
                WHERE ID = ?
            """, (
                person.get("email"), person.get("last_name"),
                person.get("email_status"),
                1 if person.get("email_domain_catchall") else 0,
                person.get("linkedin_url"), domain,
                org.get("estimated_num_employees"), org.get("industry"),
                person.get("city"), person.get("state"), person.get("country"),
                org.get("phone"), pixel, t["ID"],
            ))
            conn.commit()   # persist each reveal immediately: crash-safe + releases the lock
            revealed += 1
            catchall = " ⚠ catch-all" if person.get("email_domain_catchall") else ""
            print(f"   ✅ {t['First_Name']} {person.get('last_name','')} @ {t['Org_Name']} "
                  f"→ {person.get('email')}  [pixel: {pixel}]{catchall}")
        else:
            print(f"   ○ No match for {t['First_Name']} @ {t['Org_Name']} (0 credits)")
    conn.commit()
    conn.close()
    print(f"\n🏁 Revealed {revealed}/{len(targets)} emails.")
    cost_tracker.spend_report()


def _ensure_main_columns(mconn):
    """Additively add the columns US leads need on company_enrichment. Idempotent."""
    for ddl in (
        "ALTER TABLE company_enrichment ADD COLUMN Company_Name TEXT",
        "ALTER TABLE company_enrichment ADD COLUMN Lead_Source TEXT",
    ):
        try:
            mconn.execute(ddl)
        except sqlite3.OperationalError:
            pass  # column already exists


def run_export():
    """
    Push export-ready US leads into the MAIN pipeline DB.
      Gate:    enriched + Pixel_Status='yes' (if QUALIFY_REQUIRES_PIXEL) + not catch-all.
      Target:  company_contacts (person, primary) + company_enrichment (company).
      CIN:     synthetic 'APOLLO_<person_id>'.
      Safety:  idempotent (ON CONFLICT), local Exported_At guard, fully reversible
               via  DELETE FROM company_contacts  WHERE CIN LIKE 'APOLLO_%';
                    DELETE FROM company_enrichment WHERE CIN LIKE 'APOLLO_%';
    """
    conn = get_conn()
    cur = conn.cursor()

    where = "Enriched_At IS NOT NULL AND Exported_At IS NULL AND Email_Catchall = 0"
    if QUALIFY_REQUIRES_PIXEL:
        where += " AND Pixel_Status = 'yes'"

    cur.execute(f"""
        SELECT ID, Apollo_Person_ID, First_Name, Last_Name, Title, Email,
               LinkedIn_URL, Org_Name, Org_Domain, Phone
        FROM us_leads WHERE {where}
    """)
    rows = cur.fetchall()

    if not rows:
        print("   No export-ready leads (need: enriched, pixel=yes, not catch-all, "
              "not already exported).")
        conn.close()
        return

    mconn = sqlite3.connect(MAIN_DB_PATH)
    _ensure_main_columns(mconn)
    mcur = mconn.cursor()

    exported = 0
    for r in rows:
        cin = f"APOLLO_{r['Apollo_Person_ID']}"
        full_name = f"{r['First_Name'] or ''} {r['Last_Name'] or ''}".strip()

        # Company row — mark pixel-confirmed and intelligence-ready for the sender.
        mcur.execute("""
            INSERT INTO company_enrichment
                (CIN, Company_Name, Website_URL, Phone, Domain_Source,
                 Has_Google_Ads_Pixel, Pipeline_Status, Lead_Source)
            VALUES (?, ?, ?, ?, 'Apollo', 1, 'Intelligence_Ready', 'US_Apollo')
            ON CONFLICT(CIN) DO UPDATE SET
                Company_Name = excluded.Company_Name,
                Website_URL  = excluded.Website_URL,
                Phone        = excluded.Phone,
                Has_Google_Ads_Pixel = 1,
                Lead_Source  = 'US_Apollo'
        """, (cin, r['Org_Name'], r['Org_Domain'], r['Phone']))

        # Contact row — primary; skip if this email already exists for the CIN.
        dup = mcur.execute(
            "SELECT 1 FROM company_contacts WHERE CIN = ? AND Email_Address = ?",
            (cin, r['Email']),
        ).fetchone()
        if not dup:
            mcur.execute("""
                INSERT INTO company_contacts
                    (CIN, Full_Name, Job_Title, Email_Address, Email_Label,
                     LinkedIn_URL, Is_Primary_Contact)
                VALUES (?, ?, ?, ?, 'Work', ?, 1)
            """, (cin, full_name, r['Title'], r['Email'], r['LinkedIn_URL']))

        mconn.commit()
        conn.execute("UPDATE us_leads SET Exported_At = CURRENT_TIMESTAMP WHERE ID = ?",
                     (r['ID'],))
        conn.commit()
        exported += 1
        print(f"   → exported {full_name} @ {r['Org_Name']} → {cin}")

    mconn.close()
    conn.close()
    print(f"\n🏁 Exported {exported} lead(s) into the main pipeline "
          f"(company_contacts + company_enrichment).")
    print("   Reversible: DELETE FROM company_contacts/company_enrichment WHERE CIN LIKE 'APOLLO_%';")


def main():
    ap = argparse.ArgumentParser(description="US agency lead discovery via Apollo")
    ap.add_argument("--dry-run", action="store_true", help="Search + qualify, 0 credits")
    ap.add_argument("--enrich", type=int, metavar="N", help="Reveal N qualified emails")
    ap.add_argument("--cost", action="store_true", help="Show spend report")
    ap.add_argument("--export", action="store_true", help="Push qualified leads to main pipeline")
    ap.add_argument("--send", type=int, metavar="N", help="Send up to N US emails (warmup-capped)")
    ap.add_argument("--test", metavar="EMAIL", help="With --send: route all emails to this address")
    ap.add_argument("--send-dry", action="store_true", help="With --send: render without sending")
    ap.add_argument("--seed-campaigns", action="store_true", help="Seed US email arms into campaign_templates")
    args = ap.parse_args()

    if args.cost:
        cost_tracker.spend_report()
    elif args.enrich:
        run_enrich(args.enrich)
    elif args.export:
        run_export()
    elif args.seed_campaigns:
        from . import seed_campaigns
        seed_campaigns.seed()
    elif args.send is not None:
        from . import sender
        sender.run(count=args.send, test_email=args.test, dry_run=args.send_dry)
    else:
        run_search()


if __name__ == "__main__":
    main()
