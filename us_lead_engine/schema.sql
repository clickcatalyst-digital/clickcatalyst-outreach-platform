-- us_lead_engine/schema.sql
-- Independent tables. Nothing here touches the main pipeline until export.

CREATE TABLE IF NOT EXISTS us_leads (
    ID                  INTEGER PRIMARY KEY AUTOINCREMENT,
    Apollo_Person_ID    TEXT UNIQUE NOT NULL,
    First_Name          TEXT,
    Last_Name           TEXT,             -- NULL until enriched (masked in search)
    Title               TEXT,
    Email               TEXT,             -- NULL until enriched (1 credit)
    Email_Status        TEXT,             -- verified / likely / unavailable
    Email_Catchall      INTEGER,          -- 1 = catch-all domain (deliverability risk), set at enrich
    LinkedIn_URL        TEXT,
    Org_Name            TEXT,
    Org_Domain          TEXT,             -- NULL until enriched
    Org_Employee_Count  INTEGER,          -- NULL until enriched
    Org_Industry        TEXT,
    City                TEXT,             -- NULL until enriched
    State               TEXT,
    Country             TEXT,
    Phone               TEXT,
    Source_Query        TEXT,             -- which ICP search found this lead
    Has_Email_Flag      INTEGER,          -- has_email from search (1 = revealable)
    Has_Direct_Phone    TEXT,             -- has_direct_phone hint from search
    -- Free pre-reveal qualification (title + search-time filters)
    Role_Score          INTEGER,          -- 0-100 from role_classifier
    Role_Label          TEXT,             -- DECISION_MAKER / MARKETING_LEADER / ...
    Qualified           INTEGER DEFAULT 0,-- passed the free pre-reveal gate
    -- Post-reveal qualification (precise pixel check on revealed domain)
    Pixel_Status        TEXT,             -- yes / no / unchecked / unreachable
    -- Lifecycle
    Discovered_At       DATETIME DEFAULT CURRENT_TIMESTAMP,
    Enriched_At         DATETIME,         -- set when email revealed
    Exported_At         DATETIME          -- set when pushed to company_contacts
);

CREATE INDEX IF NOT EXISTS idx_us_leads_domain ON us_leads(Org_Domain);
CREATE INDEX IF NOT EXISTS idx_us_leads_qualified ON us_leads(Qualified);

-- Cost log: one row per API call (concern #2).
CREATE TABLE IF NOT EXISTS api_usage_log (
    ID              INTEGER PRIMARY KEY AUTOINCREMENT,
    Provider        TEXT DEFAULT 'apollo',
    Endpoint        TEXT,                 -- mixed_people/search | people/match
    Call_Type       TEXT,                 -- search | reveal
    Credits_Used    INTEGER DEFAULT 0,
    Results_Returned INTEGER DEFAULT 0,
    Emails_Revealed INTEGER DEFAULT 0,
    Plan            TEXT,                 -- plan at time of call
    USD_Cost        REAL DEFAULT 0,
    Notes           TEXT,
    Created_At      DATETIME DEFAULT CURRENT_TIMESTAMP
);
