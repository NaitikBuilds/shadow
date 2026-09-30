-- 002_ambient_task_state.sql
-- Persists dismiss/promote decisions for the Ambient Task List.

CREATE TABLE IF NOT EXISTS ambient_task_state (
    entity_id INTEGER PRIMARY KEY,
    status TEXT NOT NULL,             -- 'dismissed' | 'promoted'
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ambient_status ON ambient_task_state(status);