-- 009_clone_sessions.sql
-- Metadata only — clone CONTENT lives in ephemeral in-memory stores (DR-P4-10).
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS clone_sessions (
    clone_id        TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    scope_json      TEXT NOT NULL,
    status          TEXT NOT NULL
                    CHECK(status IN ('active','discarding','discarded','expired')),
    include_values  INTEGER NOT NULL DEFAULT 0,
    created_at      INTEGER NOT NULL,
    ended_at        INTEGER,
    schema_version  INTEGER NOT NULL DEFAULT 1
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_clone_active_name
    ON clone_sessions(name) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_clone_status ON clone_sessions(status);

CREATE TABLE IF NOT EXISTS clone_promotions (
    promotion_id  INTEGER PRIMARY KEY,
    clone_id      TEXT NOT NULL,
    artifact_id   TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    note_ref      INTEGER,
    promoted_at   INTEGER NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_clone_promo_hash
    ON clone_promotions(content_hash);
CREATE UNIQUE INDEX IF NOT EXISTS idx_clone_promo_pair
    ON clone_promotions(clone_id, artifact_id);

UPDATE schema_meta SET value = '9' WHERE key = 'current_version';