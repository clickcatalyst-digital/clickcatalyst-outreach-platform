-- Async discover jobs (search jobs triggered from UI)
CREATE TABLE IF NOT EXISTS discover_jobs (
    Job_ID          INTEGER PRIMARY KEY AUTOINCREMENT,
    Query_Text      TEXT NOT NULL,
    City_Hint       TEXT,            -- if user picked a city, store it for location_bias
    Status          TEXT DEFAULT 'pending',  -- pending | running | done | failed
    Created_At      DATETIME DEFAULT CURRENT_TIMESTAMP,
    Started_At      DATETIME,
    Finished_At     DATETIME,
    Leads_Returned  INTEGER DEFAULT 0,
    Leads_New       INTEGER DEFAULT 0,
    Leads_HighQ     INTEGER DEFAULT 0,
    Error_Message   TEXT
);

CREATE INDEX IF NOT EXISTS idx_discover_jobs_status ON discover_jobs(Status);
CREATE INDEX IF NOT EXISTS idx_discover_jobs_created ON discover_jobs(Created_At DESC);