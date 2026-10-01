"""Focus Patterns — learn when and where you focus best.

Reads historical typing_dynamics observations, groups them by
(weekday, hour) and by process, computes average focus score per
bucket, and surfaces the strongest patterns as insights.

No new tables. Computed on demand.
"""

import json
from collections import defaultdict
from datetime import datetime, timedelta

from .insight import Insight

# Require at least this many samples for a bucket to be considered.
MIN_SAMPLES = 10

# Require at least this many samples for a pattern to be "fully confident".
FULL_SAMPLES = 40

# Lookback window for pattern analysis.
LOOKBACK_DAYS = 30

# Minimum mean focus for a bucket to be considered a "best" pattern.
MIN_FOCUS_SCORE = 0.65


_WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


class FocusPatternsEngine:
    """Analyzes typing dynamics to find when and where focus is highest."""

    def __init__(self, memory):
        self.memory = memory

    # ---------- public API ----------

    def find_patterns(self, limit: int = 3) -> list[Insight]:
        rows = self._load_typing_rows()
        if not rows:
            return []

        time_buckets = self._bucket_by_time(rows)
        process_buckets = self._bucket_by_process(rows)

        insights: list[Insight] = []
        insights.extend(self._time_insights(time_buckets))
        insights.extend(self._process_insights(process_buckets))

        # Sort by score, dedupe by title
        best: dict[str, Insight] = {}
        for i in insights:
            if i.title not in best or i.score > best[i.title].score:
                best[i.title] = i

        ordered = sorted(best.values(), key=lambda i: i.score, reverse=True)
        return ordered[:limit]

    # ---------- internals ----------

    def _load_typing_rows(self) -> list[dict]:
        cutoff = (datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)).isoformat(
            sep=" ", timespec="seconds"
        )

        try:
            cur = self.memory.conn.cursor()
            cur.execute(
                "SELECT timestamp, metadata FROM observations "
                "WHERE source = 'typing_dynamics' AND timestamp >= ? "
                "ORDER BY timestamp ASC",
                (cutoff,),
            )
            raw = cur.fetchall()
        except Exception:
            return []

        rows: list[dict] = []
        for ts, metadata in raw:
            try:
                parsed = datetime.fromisoformat(ts)
            except (TypeError, ValueError):
                continue
            score = self._extract_focus(metadata)
            if score is None:
                continue
            rows.append({"timestamp": parsed, "focus_score": score})
        return rows

    @staticmethod
    def _extract_focus(metadata: str | None) -> float | None:
        if not metadata:
            return None
        try:
            data = json.loads(metadata)
        except (TypeError, ValueError):
            return None
        raw = data.get("focus_score")
        if raw is None:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    def _bucket_by_time(self, rows: list[dict]) -> dict[tuple, list[float]]:
        buckets: dict[tuple, list[float]] = defaultdict(list)
        for r in rows:
            key = (r["timestamp"].weekday(), r["timestamp"].hour)
            buckets[key].append(r["focus_score"])
        return buckets

    def _bucket_by_process(self, rows: list[dict]) -> dict[str, list[float]]:
        """Bucket typing observations by the process active at that time."""
        # We approximate by joining each typing row to the nearest
        # active_window observation within ±5 minutes.
        buckets: dict[str, list[float]] = defaultdict(list)
        try:
            cur = self.memory.conn.cursor()
            cur.execute(
                "SELECT timestamp, content FROM observations "
                "WHERE source = 'active_window' AND timestamp >= ? "
                "ORDER BY timestamp ASC",
                (
                    (datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)).isoformat(
                        sep=" ", timespec="seconds"
                    ),
                ),
            )
            window_rows = cur.fetchall()
        except Exception:
            return {}

        parsed_windows: list[tuple[datetime, str]] = []
        for ts, content in window_rows:
            try:
                parsed = datetime.fromisoformat(ts)
            except (TypeError, ValueError):
                continue
            process = self._extract_process(content or "")
            if process:
                parsed_windows.append((parsed, process))

        if not parsed_windows:
            return {}

        for row in rows:
            process = self._nearest_process(row["timestamp"], parsed_windows)
            if process:
                buckets[process].append(row["focus_score"])
        return buckets

    @staticmethod
    def _extract_process(content: str) -> str:
        """Active window content is 'process.exe: Title'. Extract the process."""
        if not content:
            return ""
        head = content.split(":", 1)[0].strip()
        if head.lower().endswith(".exe"):
            return head[:-4]
        return head

    @staticmethod
    def _nearest_process(ts: datetime, windows: list[tuple[datetime, str]]) -> str:
        """Find the active window closest in time to ts (within 5 min)."""
        if not windows:
            return ""
        best = None
        best_delta = timedelta(minutes=5)
        for wts, process in windows:
            delta = abs(ts - wts)
            if delta < best_delta:
                best_delta = delta
                best = process
        return best or ""

    # ---------- insights ----------

    def _time_insights(self, buckets: dict[tuple, list[float]]) -> list[Insight]:
        insights: list[Insight] = []
        for (weekday, hour), scores in buckets.items():
            if len(scores) < MIN_SAMPLES:
                continue
            mean = sum(scores) / len(scores)
            if mean < MIN_FOCUS_SCORE:
                continue
            confidence = min(1.0, len(scores) / FULL_SAMPLES)
            score = round(mean * confidence, 2)
            weekday_name = _WEEKDAYS[weekday]
            time_label = self._hour_label(hour)
            insights.append(
                Insight(
                    kind="focus_pattern_time",
                    title=f"Sharpest: {weekday_name} {time_label}",
                    body=(
                        f"Your average focus around {weekday_name} "
                        f"{time_label} is {mean:.2f} across "
                        f"{len(scores)} sessions."
                    ),
                    score=score,
                    action="Schedule deep work here",
                )
            )
        return insights

    def _process_insights(self, buckets: dict[str, list[float]]) -> list[Insight]:
        insights: list[Insight] = []
        for process, scores in buckets.items():
            if len(scores) < MIN_SAMPLES:
                continue
            mean = sum(scores) / len(scores)
            if mean < MIN_FOCUS_SCORE:
                continue
            confidence = min(1.0, len(scores) / FULL_SAMPLES)
            score = round(mean * confidence, 2)
            insights.append(
                Insight(
                    kind="focus_pattern_process",
                    title=f"Focused in: {process}",
                    body=(
                        f"Your average focus in {process} is {mean:.2f} "
                        f"across {len(scores)} samples."
                    ),
                    score=score,
                    action="Protect these sessions",
                )
            )
        return insights

    @staticmethod
    def _hour_label(hour: int) -> str:
        if hour < 6:
            return "late night"
        if hour < 9:
            return "early morning"
        if hour < 12:
            return "mornings"
        if hour < 14:
            return "midday"
        if hour < 17:
            return "afternoons"
        if hour < 20:
            return "evenings"
        return "nights"
