-- Make Run_ID nullable to support ad-hoc searches from Discover UI

-- Step 1: Rename existing table
ALTER TABLE bulk_run_queries RENAME TO bulk_run_queries_old;

-- Step 2: Recreate with nullable Run_ID
CREATE TABLE bulk_run_queries (
    Query_ID        INTEGER PRIMARY KEY AUTOINCREMENT,
    Run_ID          INTEGER,                          -- nullable now: NULL = ad-hoc search
    Query_Text      TEXT NOT NULL,
    City            TEXT,
    Status          TEXT DEFAULT 'pending',
    Leads_Returned  INTEGER DEFAULT 0,
    Leads_New       INTEGER DEFAULT 0,
    Error           TEXT,
    Executed_At     DATETIME,
    FOREIGN KEY (Run_ID) REFERENCES bulk_run_history(Run_ID)
);

-- Step 3: Copy old data
INSERT INTO bulk_run_queries
SELECT * FROM bulk_run_queries_old;

-- Step 4: Drop old table
DROP TABLE bulk_run_queries_old;

-- Step 5: Recreate index
CREATE INDEX IF NOT EXISTS idx_bulk_queries_run ON bulk_run_queries(Run_ID);