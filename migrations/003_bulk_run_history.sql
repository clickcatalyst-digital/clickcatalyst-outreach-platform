CREATE TABLE IF NOT EXISTS bulk_run_history (
    Run_ID          INTEGER PRIMARY KEY AUTOINCREMENT,
    Started_At      DATETIME DEFAULT CURRENT_TIMESTAMP,
    Finished_At     DATETIME,
    Config_Name     TEXT,
    Total_Queries   INTEGER,
    Successful      INTEGER DEFAULT 0,
    Failed          INTEGER DEFAULT 0,
    Total_Leads     INTEGER DEFAULT 0,
    New_Leads       INTEGER DEFAULT 0,
    Status          TEXT DEFAULT 'running',   -- 'running' | 'done' | 'aborted'
    Error_Log       TEXT
);

CREATE TABLE IF NOT EXISTS bulk_run_queries (
    Query_ID        INTEGER PRIMARY KEY AUTOINCREMENT,
    Run_ID          INTEGER NOT NULL,
    Query_Text      TEXT NOT NULL,
    City            TEXT,
    Status          TEXT DEFAULT 'pending',   -- 'pending' | 'success' | 'failed' | 'skipped'
    Leads_Returned  INTEGER DEFAULT 0,
    Leads_New       INTEGER DEFAULT 0,
    Error           TEXT,
    Executed_At     DATETIME,
    FOREIGN KEY (Run_ID) REFERENCES bulk_run_history(Run_ID)
);

CREATE INDEX IF NOT EXISTS idx_bulk_queries_run ON bulk_run_queries(Run_ID);