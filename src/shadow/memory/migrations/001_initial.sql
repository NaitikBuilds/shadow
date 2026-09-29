-- 001_initial.sql
-- Baseline schema as of Phase 2 (perception complete).
-- All statements use IF NOT EXISTS for idempotency and for retrofit
-- of databases created before the migration framework existed.

-- ─── Observations ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    source TEXT,
    content TEXT,
    metadata TEXT
);

-- ─── Intentions ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS intentions (
    id INTEGER PRIMARY KEY,
    description TEXT,
    status TEXT,
    due DATETIME,
    confidence REAL
);

-- ─── Activity log ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    action TEXT,
    details TEXT
);

-- ─── Vector store ────────────────────────────────────────────────
CREATE VIRTUAL TABLE IF NOT EXISTS vec_observations USING vec0(
    embedding float[384]
);

-- ─── Consents ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS consents (
    channel TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 0,
    scope TEXT DEFAULT 'global',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS consent_audit (
    id INTEGER PRIMARY KEY,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    channel TEXT,
    action TEXT,
    reason TEXT
);

-- ─── Knowledge graph ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
    mention_count INTEGER DEFAULT 1,
    UNIQUE(type, name)
);

CREATE TABLE IF NOT EXISTS edges (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    relation TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_id, target_id, relation),
    FOREIGN KEY(source_id) REFERENCES entities(id) ON DELETE CASCADE,
    FOREIGN KEY(target_id) REFERENCES entities(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS observation_entities (
    observation_id INTEGER NOT NULL,
    entity_id INTEGER NOT NULL,
    PRIMARY KEY (observation_id, entity_id),
    FOREIGN KEY(observation_id) REFERENCES observations(id) ON DELETE CASCADE,
    FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE
);

-- ─── Indexes ─────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
CREATE INDEX IF NOT EXISTS idx_obs_entities_obs ON observation_entities(observation_id);
CREATE INDEX IF NOT EXISTS idx_obs_entities_ent ON observation_entities(entity_id);