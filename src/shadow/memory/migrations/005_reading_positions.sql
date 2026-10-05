-- 005_reading_positions.sql
-- Tracks reading positions in long documents for "resume reading" insights.

CREATE TABLE IF NOT EXISTS reading_positions (
    id INTEGER PRIMARY KEY,
    identifier TEXT NOT NULL,
    title TEXT NOT NULL,
    position_pct REAL DEFAULT 0,
    section TEXT DEFAULT '',
    first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(identifier)
);

CREATE INDEX IF NOT EXISTS idx_reading_updated
    ON reading_positions(updated_at);