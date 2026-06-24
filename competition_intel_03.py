# competition_intel_03.py
# The Intelligence & Outreach Engine
# Input:  Golden Leads only — Tier 1 + Has_Google_Ads_Pixel = 1
# Action 1: Generate competitor intelligence + personalized email sentence
# Action 2: Save competitor scatter plot data to competitor_analysis_data
# Action 3: Log intelligence back to company_enrichment
# Next step: email_engine.py reads this data and renders + sends the email

import sqlite3
import pandas as pd
from datetime import date

DB_PATH = '/Users/pujan/Developer/data_collector/indian_companies/company_master_data.db'

# ---------------------------------------------------------------------------
# ACTION 1: Competitor Intelligence + Email Sentence
# ---------------------------------------------------------------------------

def get_competitor_intelligence(cin, db_path=DB_PATH):
    """
    Takes a target CIN, finds strict competitors, generates personalized email copy.
    Returns a dict with all intelligence needed by downstream functions.
    """
    conn = sqlite3.connect(db_path)

    query = """
    SELECT
        Target.CIN                  AS Target_CIN,
        Target.CompanyName          AS Target_Name,
        Target.PaidupCapital        AS Target_Capital,
        Target.RegistrationDate     AS Target_RegDate,
        Target.State                AS State,
        Target.nic_code             AS NIC_Code,
        n.description               AS Industry,
        Competitor.CIN              AS Competitor_CIN,
        Competitor.CompanyName      AS Competitor_Name,
        Competitor.PaidupCapital    AS Competitor_Capital,
        Competitor.RegistrationDate AS Competitor_RegDate
    FROM vw_qualified_leads Target
    JOIN vw_qualified_leads Competitor
        ON  Target.State     = Competitor.State
        AND Target.nic_code  = Competitor.nic_code
        AND Target.CIN      != Competitor.CIN
    LEFT JOIN nic_master n
        ON Target.nic_code = n.nic_code_5d
    WHERE Target.CIN = ?
        AND CAST(Competitor.PaidupCapital AS REAL)
            BETWEEN (CAST(Target.PaidupCapital AS REAL) * 0.5)
                AND (CAST(Target.PaidupCapital AS REAL) * 1.5)
        AND ABS(julianday(Target.RegistrationDate) - julianday(Competitor.RegistrationDate)) <= 365;
    """

    df = pd.read_sql_query(query, conn, params=(cin,))
    conn.close()

    # --- Fallback: no strict competitors found ---
    if df.empty:
        return {
            "target_cin": cin,
            "target_name": None,
            "competitor_count": 0,
            "email_sentence": (
                "I noticed your recent Google Ads activity and identified some efficiency gaps "
                "compared to standard industry benchmarks."
            ),
            "competitors_df": pd.DataFrame(),
            "benchmark_avg": None
        }

    target_name      = df['Target_Name'].iloc[0].title()
    target_capital   = float(df['Target_Capital'].iloc[0])
    target_reg_date  = df['Target_RegDate'].iloc[0]
    industry         = df['Industry'].iloc[0].lower() if df['Industry'].iloc[0] else "industry"
    state            = df['State'].iloc[0].title()
    competitor_count = len(df)

    # Benchmark: average capital of the competitor cohort
    benchmark_avg = df['Competitor_Capital'].astype(float).mean()

    # Cap display count so we don't sound like a surveillance operation
    display_count = f"over 15" if competitor_count > 15 else str(competitor_count)

    email_sentence = (
        f"While {target_name} is running a solid search campaign, my analysis shows "
        f"{display_count} other {industry} companies in {state} with your exact capital bracket "
        f"are currently capturing impression share."
    )

    return {
        "target_cin":        cin,
        "target_name":       target_name,
        "target_capital":    target_capital,
        "target_reg_date":   target_reg_date,
        "competitor_count":  competitor_count,
        "email_sentence":    email_sentence,
        "competitors_df":    df,
        "benchmark_avg":     benchmark_avg,
        "industry":          industry,
        "state":             state
    }


# ---------------------------------------------------------------------------
# ACTION 2: Save Scatter Plot Data
# ---------------------------------------------------------------------------

def save_competitor_scatter_data(intelligence, db_path=DB_PATH):
    """
    Populates competitor_analysis_data for the target + all competitors.
    - Pulls pixel status for competitors already in company_enrichment (free win)
    - Marks unknown competitors as NULL (not grey — let the plot handle styling)
    - Repeats Industry_Benchmark_Avg on every row for zero-join plot rendering
    """
    if intelligence['competitors_df'].empty:
        print(f"   [Scatter] No competitors found for {intelligence['target_cin']} — skipping.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    df           = intelligence['competitors_df']
    target_cin   = intelligence['target_cin']
    benchmark    = intelligence['benchmark_avg']
    today        = date.today()

    # Pull pixel status for any competitor already enriched in our pipeline
    competitor_cins = df['Competitor_CIN'].tolist()
    placeholders    = ','.join(['?'] * len(competitor_cins))
    pixel_lookup    = {}

    if competitor_cins:
        rows = cursor.execute(
            f"SELECT CIN, Has_Google_Ads_Pixel FROM company_enrichment WHERE CIN IN ({placeholders})",
            competitor_cins
        ).fetchall()
        pixel_lookup = {row[0]: row[1] for row in rows}

    # Delete stale data for this target before inserting fresh batch
    cursor.execute(
        "DELETE FROM competitor_analysis_data WHERE Target_CIN = ?", (target_cin,)
    )

    rows_to_insert = []

    # --- Insert target row (Is_Target_Lead = 1) ---
    target_age = (today - pd.to_datetime(intelligence['target_reg_date']).date()).days
    rows_to_insert.append((
        target_cin,
        target_cin,
        intelligence['target_name'],
        intelligence['target_capital'],
        target_age,
        1,   # Has_Pixel — confirmed True (golden lead filter guarantees this)
        1,   # Is_Target_Lead
        benchmark
    ))

    # --- Insert competitor rows (Is_Target_Lead = 0) ---
    for _, row in df.iterrows():
        comp_cin   = row['Competitor_CIN']
        comp_age   = (today - pd.to_datetime(row['Competitor_RegDate']).date()).days
        comp_pixel = pixel_lookup.get(comp_cin, None)  # NULL if not in our pipeline

        rows_to_insert.append((
            target_cin,
            comp_cin,
            row['Competitor_Name'].title(),
            float(row['Competitor_Capital']),
            comp_age,
            comp_pixel,
            0,   # Is_Target_Lead
            benchmark
        ))

    cursor.executemany("""
        INSERT INTO competitor_analysis_data
            (Target_CIN, Competitor_CIN, Competitor_Name, Capital,
             Age_In_Days, Has_Pixel, Is_Target_Lead, Industry_Benchmark_Avg, Captured_At)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows_to_insert)

    conn.commit()
    conn.close()
    print(f"   [Scatter] Saved {len(rows_to_insert)} rows for {target_cin} (1 target + {len(rows_to_insert)-1} competitors)")


# ---------------------------------------------------------------------------
# ACTION 3: Log Intelligence to company_enrichment
# ---------------------------------------------------------------------------

def log_outreach_intelligence(intelligence, db_path=DB_PATH):
    """
    Saves generated intelligence to company_enrichment.
    Does NOT mark Email_Sent_Date — that's the email engine's job.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE company_enrichment
        SET Competitor_Count       = ?,
            Personalized_Sentence  = ?,
            Pipeline_Status        = 'Intelligence_Ready'
        WHERE CIN = ?;
    """, (
        intelligence['competitor_count'],
        intelligence['email_sentence'],
        intelligence['target_cin']
    ))

    conn.commit()
    conn.close()
    print(f"   [Log] Intelligence saved for {intelligence['target_cin']} — status: Intelligence_Ready")


# ---------------------------------------------------------------------------
# BATCH RUNNER
# ---------------------------------------------------------------------------

def run_intelligence_batch(batch_size=50, db_path=DB_PATH):
    """
    Pulls Golden Leads (Tier 1 + pixel confirmed + not yet intelligence-processed),
    runs all three actions for each, in sequence.
    """
    print("🧠 INITIALIZING INTELLIGENCE ENGINE 🧠\n")

    conn = sqlite3.connect(db_path)

    df_targets = pd.read_sql_query("""
        SELECT q.CIN, q.CompanyName, q.State
        FROM vw_qualified_leads q
        JOIN company_enrichment e ON q.CIN = e.CIN
        WHERE q.ICP_Segment      = 'Tier 1: Brand - High Intent (Direct Buyers)'
        AND e.Has_Google_Ads_Pixel = 1
        AND e.Website_URL         IS NOT NULL
        AND e.Domain_Source       != 'Failed / Not Found'
        AND (e.Pipeline_Status    = 'Enriched_Ready' OR e.Pipeline_Status IS NULL)
        AND (e.Unsubscribed IS NULL OR e.Unsubscribed = 0)
        LIMIT ?;
    """, conn, params=(batch_size,))

    conn.close()

    if df_targets.empty:
        print("No golden leads pending intelligence. All caught up!")
        return

    print(f"Loaded {len(df_targets)} golden leads. Starting analysis...\n")

    success_count = 0

    for _, row in df_targets.iterrows():
        cin  = row['CIN']
        name = row['CompanyName']
        print("=" * 60)
        print(f"Processing: {name} ({cin})")

        # Action 1: Generate intelligence
        intelligence = get_competitor_intelligence(cin, db_path)
        print(f"   [Intel] {intelligence['competitor_count']} competitors found")
        print(f"   [Intel] {intelligence['email_sentence']}")

        # Action 2: Save scatter plot data
        save_competitor_scatter_data(intelligence, db_path)

        # Action 3: Log to company_enrichment
        log_outreach_intelligence(intelligence, db_path)

        success_count += 1

    print("=" * 60)
    print(f"🏁 INTELLIGENCE BATCH COMPLETE — {success_count}/{len(df_targets)} leads processed.")


# --- Execute ---
# run_intelligence_batch()