-- 004_tab_state.sql
-- Tracks open tabs across browser and terminal windows.

CREATE TABLE IF NOT EXISTS tab_state (
    id INTEGER PRIMARY KEY,
    window_process TEXT NOT NULL,
    tab_title TEXT NOT NULL,
    first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_active DATETIME,
    UNIQUE(window_process, tab_title)
);

CREATE INDEX IF NOT EXISTS idx_tab_state_last_seen
    ON tab_state(last_seen);
CREATE INDEX IF NOT EXISTS idx_tab_state_process
    ON tab_state(window_process);