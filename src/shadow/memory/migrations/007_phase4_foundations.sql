-- 007_phase4_foundations.sql
-- Phase 4 Stage A bookkeeping only. Feature tables land in later migrations.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS p4_retention_meta (
    table_name   TEXT PRIMARY KEY,
    policy_json  TEXT NOT NULL,
    created_at   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS p4_wipe_meta (
    table_name    TEXT PRIMARY KEY,
    registered_at INTEGER NOT NULL
);

-- schema_meta is key/value: (key TEXT PRIMARY KEY, value TEXT).
-- The runner may also bump this itself; this UPDATE is safe either way.
UPDATE schema_meta SET value = '7' WHERE key = 'current_version';