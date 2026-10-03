"""Insight Feedback — captures user verdicts on insights.

Stores 'useful' / 'not_useful' verdicts in insight_feedback and computes
the useful intervention rate (the PRD's primary Level 4 metric).

No auto-demotion yet. The goal of this commit is data collection so the
rate can be measured and, later, low-value insights can be tuned out.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class FeedbackStats:
    total: int
    useful: int
    not_useful: int
    rate: float  # useful / total; 1.0 if no data
    window_days: int


class FeedbackStore:
    """Records and aggregates insight feedback."""

    DEFAULT_WINDOW_DAYS = 30

    def __init__(self, memory):
        self.memory = memory

    # ---------- public API ----------

    def title_hash(self, title: str) -> str:
        normalized = " ".join(title.lower().split())
        return hashlib.sha1(normalized.encode()).hexdigest()[:16]

    def record(self, kind: str, title: str, verdict: str) -> None:
        """Record a verdict ('useful' or 'not_useful') for an insight."""
        if verdict not in ("useful", "not_useful"):
            raise ValueError(f"invalid verdict: {verdict}")
        if not kind or not title:
            return

        with self.memory._lock:
            cur = self.memory.conn.cursor()
            cur.execute(
                "INSERT INTO insight_feedback "
                "(insight_kind, title_hash, verdict) VALUES (?, ?, ?)",
                (kind, self.title_hash(title), verdict),
            )
            self.memory.conn.commit()

        try:
            self.memory.log_activity(
                "insight_feedback", f"{verdict}: {kind}: {title[:60]}"
            )
        except Exception:
            pass

    def verdict_for(self, kind: str, title: str) -> str | None:
        """Return the most recent verdict for this insight, if any."""
        cur = self.memory.conn.cursor()
        cur.execute(
            "SELECT verdict FROM insight_feedback "
            "WHERE insight_kind = ? AND title_hash = ? "
            "ORDER BY id DESC LIMIT 1",
            (kind, self.title_hash(title)),
        )
        row = cur.fetchone()
        return row[0] if row else None

    def stats(self, window_days: int | None = None) -> FeedbackStats:
        """Return useful intervention rate over a rolling window."""
        days = window_days or self.DEFAULT_WINDOW_DAYS
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat(
            sep=" ", timespec="seconds"
        )

        try:
            cur = self.memory.conn.cursor()
            cur.execute(
                "SELECT verdict, COUNT(*) FROM insight_feedback "
                "WHERE created_at >= ? GROUP BY verdict",
                (cutoff,),
            )
            counts = {v: c for v, c in cur.fetchall()}
        except Exception:
            counts = {}

        useful = counts.get("useful", 0)
        not_useful = counts.get("not_useful", 0)
        total = useful + not_useful
        rate = (useful / total) if total > 0 else 1.0

        return FeedbackStats(
            total=total,
            useful=useful,
            not_useful=not_useful,
            rate=round(rate, 3),
            window_days=days,
        )

    def stats_by_kind(self, window_days: int | None = None) -> dict[str, FeedbackStats]:
        """Return per-kind stats."""
        days = window_days or self.DEFAULT_WINDOW_DAYS
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat(
            sep=" ", timespec="seconds"
        )

        try:
            cur = self.memory.conn.cursor()
            cur.execute(
                "SELECT insight_kind, verdict, COUNT(*) "
                "FROM insight_feedback WHERE created_at >= ? "
                "GROUP BY insight_kind, verdict",
                (cutoff,),
            )
            raw = cur.fetchall()
        except Exception:
            return {}

        buckets: dict[str, dict[str, int]] = {}
        for kind, verdict, count in raw:
            buckets.setdefault(kind, {})[verdict] = count

        result: dict[str, FeedbackStats] = {}
        for kind, counts in buckets.items():
            u = counts.get("useful", 0)
            n = counts.get("not_useful", 0)
            t = u + n
            result[kind] = FeedbackStats(
                total=t,
                useful=u,
                not_useful=n,
                rate=round(u / t, 3) if t else 1.0,
                window_days=days,
            )
        return result
