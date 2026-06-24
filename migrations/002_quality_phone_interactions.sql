-- Quality score for ranking Places leads
ALTER TABLE places_leads ADD COLUMN Quality_Score INTEGER DEFAULT 0;
ALTER TABLE places_leads ADD COLUMN Quality_Reasons TEXT;  -- comma-separated tags for debugging

-- Formatted phone (raw stays in National_Phone / International_Phone)
ALTER TABLE places_leads ADD COLUMN Phone_Formatted TEXT;
ALTER TABLE company_enrichment ADD COLUMN Phone_Formatted TEXT;

-- Interaction log table (works for both MCA and Places leads via CIN)
CREATE TABLE IF NOT EXISTS lead_interactions (
    Interaction_ID  INTEGER PRIMARY KEY AUTOINCREMENT,
    CIN             TEXT NOT NULL,
    Comment         TEXT NOT NULL,
    Interacted      BOOLEAN DEFAULT 1,             -- did this interaction reach a human?
    Created_At      DATETIME DEFAULT CURRENT_TIMESTAMP,
    Created_By      TEXT DEFAULT 'ui'
);

CREATE INDEX IF NOT EXISTS idx_interactions_cin ON lead_interactions(CIN);
CREATE INDEX IF NOT EXISTS idx_interactions_created ON lead_interactions(Created_At DESC);

-- Convenience view: lead + last interaction + interaction count
CREATE VIEW IF NOT EXISTS vw_lead_interaction_summary AS
SELECT
    p.CIN,
    p.Display_Name,
    p.Phone_Formatted,
    p.Website_URI,
    p.Formatted_Address,
    p.Rating,
    p.Quality_Score,
    p.Source_Query,
    (SELECT COUNT(*) FROM lead_interactions i WHERE i.CIN = p.CIN) AS Interaction_Count,
    (SELECT MAX(Created_At) FROM lead_interactions i WHERE i.CIN = p.CIN) AS Last_Interaction_At,
    (SELECT Comment FROM lead_interactions i WHERE i.CIN = p.CIN ORDER BY Created_At DESC LIMIT 1) AS Last_Comment,
    CASE WHEN (SELECT COUNT(*) FROM lead_interactions i WHERE i.CIN = p.CIN AND i.Interacted = 1) > 0
         THEN 1 ELSE 0 END AS Has_Interacted
FROM places_leads p;