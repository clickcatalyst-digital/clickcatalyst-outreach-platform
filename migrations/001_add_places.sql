-- Add phone column to existing enrichment table
ALTER TABLE company_enrichment ADD COLUMN Phone TEXT;

-- Create places_leads table for Google-specific data
CREATE TABLE IF NOT EXISTS places_leads (
    Place_ID            TEXT PRIMARY KEY,
    CIN                 TEXT NOT NULL,           -- synthetic: 'PLACES_<place_id>' or real CIN if resolved later
    Display_Name        TEXT NOT NULL,
    Formatted_Address   TEXT,
    National_Phone      TEXT,
    International_Phone TEXT,
    Website_URI         TEXT,
    Rating              REAL,
    User_Rating_Count   INTEGER,
    Business_Status     TEXT,                    -- OPERATIONAL, CLOSED_TEMPORARILY, CLOSED_PERMANENTLY
    Primary_Type        TEXT,
    Types_JSON          TEXT,                    -- JSON array of all types
    Latitude            REAL,
    Longitude           REAL,
    Google_Maps_URI     TEXT,
    Source_Query        TEXT,                    -- which search prompt found this lead
    Discovered_At       DATETIME DEFAULT CURRENT_TIMESTAMP,
    CIN_Resolution_Status TEXT DEFAULT 'synthetic'  -- 'synthetic' | 'mca_matched' (for v2 fuzzy resolver)
);

CREATE INDEX IF NOT EXISTS idx_places_cin ON places_leads(CIN);
CREATE INDEX IF NOT EXISTS idx_places_query ON places_leads(Source_Query);
CREATE INDEX IF NOT EXISTS idx_places_status ON places_leads(Business_Status);