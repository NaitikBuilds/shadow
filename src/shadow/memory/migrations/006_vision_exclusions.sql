-- 006_vision_exclusions.sql
-- Persistent per-app vision exclusions.

CREATE TABLE IF NOT EXISTS vision_exclusions (
    id INTEGER PRIMARY KEY,
    process TEXT NOT NULL UNIQUE,
    reason TEXT DEFAULT 'user',
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vision_exclusions_process
    ON vision_exclusions(process);