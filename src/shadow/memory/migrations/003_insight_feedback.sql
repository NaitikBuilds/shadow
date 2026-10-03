-- 003_insight_feedback.sql
-- Stores user feedback on insights for computing the useful intervention rate.

CREATE TABLE IF NOT EXISTS insight_feedback (
    id INTEGER PRIMARY KEY,
    insight_kind TEXT NOT NULL,
    title_hash TEXT NOT NULL,
    verdict TEXT NOT NULL,             -- 'useful' | 'not_useful'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_feedback_kind ON insight_feedback(insight_kind);
CREATE INDEX IF NOT EXISTS idx_feedback_created ON insight_feedback(created_at);
CREATE INDEX IF NOT EXISTS idx_feedback_title ON insight_feedback(title_hash);