-- 011_weaver.sql
-- Cross-Project Insight Weaver C14: provenance, dedupe, staleness, persistence
-- Migration version 11
PRAGMA foreign_keys = ON;

-- Recreate weaver_insights with new columns and updated CHECK constraint
CREATE TABLE weaver_insights_new (
    insight_id INTEGER PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('new', 'saved', 'dismissed', 'cancelled', 'stale')),
    source_project TEXT NOT NULL,
    target_project TEXT NOT NULL,
    statement TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL DEFAULT 0,
    evidence TEXT,  -- JSON: {"source_evidence": [...], "target_evidence": [...]}
    evidence_hash TEXT,  -- SHA256 hash of normalized evidence for dedup
    conflict_flag INTEGER DEFAULT 0  -- 1 if conflicting evidence detected
);

INSERT INTO weaver_insights_new
(insight_id, status, source_project, target_project, statement, created_at, updated_at, evidence)
SELECT insight_id, status, source_project, target_project, statement, created_at, created_at, evidence
FROM weaver_insights;

DROP TABLE weaver_insights;
ALTER TABLE weaver_insights_new RENAME TO weaver_insights;

-- Recreate indexes
CREATE INDEX IF NOT EXISTS idx_weaver_status ON weaver_insights(status);
CREATE INDEX IF NOT EXISTS idx_weaver_projects ON weaver_insights(source_project, target_project);
CREATE INDEX IF NOT EXISTS idx_weaver_evidence_hash ON weaver_insights(evidence_hash);

-- Create provenance table
CREATE TABLE IF NOT EXISTS weaver_insight_sources (
    source_id INTEGER PRIMARY KEY,
    insight_id INTEGER NOT NULL REFERENCES weaver_insights(insight_id) ON DELETE CASCADE,
    observation_id INTEGER NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
    project_name TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,  -- SHA256 of observation content
    snippet TEXT,  -- Redacted excerpt (<=200 chars)
    is_untrusted INTEGER DEFAULT 0,  -- 1 if tagged as untrusted source
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_weaver_sources_insight ON weaver_insight_sources(insight_id);
CREATE INDEX IF NOT EXISTS idx_weaver_sources_obs ON weaver_insight_sources(observation_id);
CREATE INDEX IF NOT EXISTS idx_weaver_sources_untrusted ON weaver_insight_sources(is_untrusted);

UPDATE schema_meta SET value = '11' WHERE key = 'current_version';