"""Intention Forecasting — predicts near-term needs.

Combines three signals:
  1. Upcoming calendar events (next 30 min)
  2. Session continuity (what you were just working on)
  3. Weekly patterns (same weekday/hour historically)

Produces Insight objects with confidence scores. No LLM call; pure
heuristics so the feature stays fast and deterministic.
"""

from collections import Counter
from datetime import datetime, timedelta

from .insight import Insight


class ForecastingEngine:
    """Predicts what the user will likely need in the next 30-120 minutes."""

    CALENDAR_HORIZON_MIN = 30
    SESSION_WINDOW_MIN = 30
    PATTERN_LOOKBACK_DAYS = 28

    def __init__(self, memory):
        self.memory = memory

    def forecast(self, limit: int = 3) -> list[Insight]:
        candidates: list[Insight] = []
        candidates.extend(self._calendar_signals())
        candidates.extend(self._session_signals())
        candidates.extend(self._pattern_signals())

        # Dedupe by title — keep the highest score
        best: dict[str, Insight] = {}
        for insight in candidates:
            existing = best.get(insight.title)
            if existing is None or insight.score > existing.score:
                best[insight.title] = insight

        ordered = sorted(best.values(), key=lambda i: i.score, reverse=True)
        return ordered[:limit]

    # ---------- signal 1: calendar ----------

    def _calendar_signals(self) -> list[Insight]:
        now = datetime.now()

        try:
            cur = self.memory.conn.cursor()
            cur.execute(
                "SELECT timestamp, content FROM observations "
                "WHERE source = 'calendar' AND timestamp >= ? "
                "ORDER BY timestamp ASC LIMIT 10",
                ((now - timedelta(hours=1)).isoformat(sep=" ", timespec="seconds"),),
            )
            rows = cur.fetchall()
        except Exception:
            return []

        insights: list[Insight] = []
        for _ts, content in rows:
            # Calendar observation content includes "upcoming"/"ongoing"
            if "upcoming" not in (content or "").lower():
                continue
            parsed = self._parse_calendar_start(content)
            if parsed is None:
                continue
            minutes_until = (parsed - now).total_seconds() / 60.0
            if 0 < minutes_until <= self.CALENDAR_HORIZON_MIN:
                summary = self._extract_summary(content)
                score = round(0.9 - (minutes_until / 60.0), 2)
                insights.append(
                    Insight(
                        kind="forecast_calendar",
                        title=f"Upcoming: {summary}",
                        body=(
                            f'"{summary}" starts in {int(minutes_until)} minutes. '
                            f"Anything you want to prepare?"
                        ),
                        score=max(0.5, score),
                        action="Open calendar",
                    )
                )
            if len(insights) >= 2:
                break
        return insights

    # ---------- signal 2: session continuity ----------

    def _session_signals(self) -> list[Insight]:
        cutoff = (
            datetime.now() - timedelta(minutes=self.SESSION_WINDOW_MIN)
        ).isoformat(sep=" ", timespec="seconds")

        try:
            cur = self.memory.conn.cursor()
            cur.execute(
                "SELECT id, timestamp, source FROM observations "
                "WHERE timestamp >= ? AND source = 'active_window' "
                "ORDER BY timestamp DESC LIMIT 20",
                (cutoff,),
            )
            rows = cur.fetchall()
        except Exception:
            return []

        if not rows:
            return []

        # Count entity co-occurrence in the session
        entity_counts: Counter = Counter()
        for obs_id, _, _ in rows:
            try:
                for e in self.memory.entities_for_observation(obs_id):
                    if e["type"] in ("project", "file"):
                        entity_counts[(e["type"], e["name"], e["id"])] += 1
            except Exception:
                continue

        if not entity_counts:
            return []

        (etype, name, eid), count = entity_counts.most_common(1)[0]
        if count < 3:
            return []

        score = min(0.7, 0.4 + 0.05 * count)
        return [
            Insight(
                kind="forecast_session",
                title=f"Continuing: {name}",
                body=(
                    f"You've been focused on {name} for a while. "
                    f"Want to keep going or switch?"
                ),
                score=round(score, 2),
                action="Continue session",
                entity_id=eid,
            )
        ]

    # ---------- signal 3: weekly patterns ----------

    def _pattern_signals(self) -> list[Insight]:
        now = datetime.now()
        weekday = now.weekday()
        hour = now.hour

        since = (now - timedelta(days=self.PATTERN_LOOKBACK_DAYS)).isoformat(
            sep=" ", timespec="seconds"
        )

        try:
            cur = self.memory.conn.cursor()
            cur.execute(
                "SELECT id, timestamp FROM observations "
                "WHERE timestamp >= ? ORDER BY timestamp ASC",
                (since,),
            )
            rows = cur.fetchall()
        except Exception:
            return []

        # Collect entity mentions that occurred at the same weekday/hour
        entity_hits: Counter = Counter()
        entity_ids: dict = {}
        for obs_id, ts in rows:
            try:
                parsed = datetime.fromisoformat(ts)
            except (TypeError, ValueError):
                continue
            if parsed.weekday() != weekday:
                continue
            if abs(parsed.hour - hour) > 1:
                continue
            try:
                for e in self.memory.entities_for_observation(obs_id):
                    if e["type"] == "project":
                        key = (e["type"], e["name"])
                        entity_hits[key] += 1
                        entity_ids[key] = e["id"]
            except Exception:
                continue

        if not entity_hits:
            return []

        (etype, name), count = entity_hits.most_common(1)[0]
        if count < 3:
            return []

        score = min(0.5, 0.25 + 0.05 * count)
        return [
            Insight(
                kind="forecast_pattern",
                title=f"Usually now: {name}",
                body=(
                    f"This is when you normally work on {name}. "
                    f"Pick up where you left off?"
                ),
                score=round(score, 2),
                action="Open recent context",
                entity_id=entity_ids.get((etype, name)),
            )
        ]

    # ---------- parsing helpers ----------

    @staticmethod
    def _parse_calendar_start(content: str) -> datetime | None:
        """Extract 'from YYYY-MM-DD HH:MM' from a calendar observation."""
        try:
            marker = "from "
            idx = content.find(marker)
            if idx < 0:
                return None
            after = content[idx + len(marker) :]
            stamp = after[:16]  # "YYYY-MM-DD HH:MM"
            return datetime.strptime(stamp, "%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _extract_summary(content: str) -> str:
        """Pull the event summary from 'Calendar event (upcoming): X from ...'."""
        try:
            start = content.find("):")
            if start < 0:
                return "event"
            after = content[start + 2 :].strip()
            end = after.find(" from ")
            if end < 0:
                return after[:80]
            return after[:end].strip()
        except Exception:
            return "event"
