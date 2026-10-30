-- 008_ethical_values.sql
-- Ethical Mirror: user-stated values store (PRD §22.4.2 / §22.6.1).
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS ethical_values (
    value_id            INTEGER PRIMARY KEY,
    text                TEXT NOT NULL CHECK(length(text) BETWEEN 1 AND 300),
    label               TEXT,
    position            INTEGER NOT NULL,
    status              TEXT NOT NULL
                        CHECK(status IN ('active','archived'))
                        DEFAULT 'active',
    source              TEXT NOT NULL
                        CHECK(source = 'user_stated')
                        DEFAULT 'user_stated',
    onboarding_prompt_id INTEGER,
    version             INTEGER NOT NULL DEFAULT 1,
    created_at          INTEGER NOT NULL,
    updated_at          INTEGER NOT NULL
);

-- Unique among active values only; archived duplicates allowed so a user
-- can re-add a value they previously archived.
-- NOTE: SQLite lower()/trim() are ASCII-only. For non-ASCII duplicates the
-- application layer is the authority (see EthicalValuesStore.add).
CREATE UNIQUE INDEX IF NOT EXISTS idx_ethical_values_unique_active
    ON ethical_values(lower(trim(text)))
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_ethical_values_status_position
    ON ethical_values(status, position);

CREATE TABLE IF NOT EXISTS ethical_values_history (
    history_id   INTEGER PRIMARY KEY,
    value_id     INTEGER NOT NULL
                 REFERENCES ethical_values(value_id) ON DELETE CASCADE,
    old_text     TEXT NOT NULL,
    old_label    TEXT,
    change_type  TEXT NOT NULL
                 CHECK(change_type IN ('update','archive','restore')),
    changed_at   INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ethical_values_history_value
    ON ethical_values_history(value_id);

UPDATE schema_meta SET value = '8' WHERE key = 'current_version';