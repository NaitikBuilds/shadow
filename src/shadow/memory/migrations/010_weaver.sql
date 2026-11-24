-- 010_weaver.sql
-- Schema for Cross-Project Insight Weaver (C13: eligibility, exclusions, candidate generation)
-- Migration version 10
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS weaver_insights (
    insight_id INTEGER PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('new', 'saved', 'dismissed', 'cancelled')),
    source_project TEXT NOT NULL,
    target_project TEXT NOT NULL,
    statement TEXT,
    created_at INTEGER NOT NULL,
    evidence TEXT  -- JSON: {"source_evidence": [...], "target_evidence": [...]}
);

CREATE INDEX IF NOT EXISTS idx_weaver_status ON weaver_insights(status);
CREATE INDEX IF NOT EXISTS idx_weaver_projects ON weaver_insights(source_project, target_project);

UPDATE schema_meta SET value = '10' WHERE key = 'current_version';