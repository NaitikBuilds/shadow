"""Recurring Pattern Detection — find regular activity rhythms.

Looks for entities that appear at roughly the same time of week
across multiple weeks. Example: "you open GitHub every Monday
around 9 AM."

Different from Focus Patterns (which measures focus score). This
engine detects activity recurrence, not quality of focus.

No new tables. Computed on demand.
"""

from collections import defaultdict
from datetime import datetime, timedelta

from .insight import Insight

# Lookback window for pattern mining.
LOOKBACK_WEEKS = 8

# Minimum number of observations required for a pattern.
MIN_OCCURRENCES = 3

# Minimum distinct weeks the pattern must appear in.
MIN_DISTINCT_WEEKS = 3

# Time tolerance for clustering occurrences (hours).
HOUR_TOLERANCE = 2

# Entity types we care about.
RELEVANT_TYPES = ("project", "file", "topic")


class RecurringPatternEngine:
    """Detects recurring activities by (entity, weekday, hour)."""

    def __init__(self, memory):
        self.memory = memory

    # ---------- public API ----------

    def find_recurring(self, limit: int = 3) -> list[Insight]:
        rows = self._load_observations()
        if not rows:
            return []

        # entity_id -> list of (weekday, hour, week_index)
        entity_events: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
        entity_meta: dict[int, dict] = {}

        for row in rows:
            for e in row["entities"]:
                if e["type"] not in RELEVANT_TYPES:
                    continue
                weekday = row["timestamp"].weekday()
                hour = row["timestamp"].hour
                week_index = self._week_index(row["timestamp"])
                entity_events[e["id"]].append((weekday, hour, week_index))
                entity_meta[e["id"]] = e

        candidates: list[Insight] = []
        for eid, events in entity_events.items():
            insight = self._analyze_entity(eid, events, entity_meta[eid])
            if insight is not None:
                candidates.append(insight)

        candidates.sort(key=lambda i: i.score, reverse=True)
        return candidates[:limit]

    # ---------- internals ----------

    def _load_observations(self) -> list[dict]:
        cutoff = (datetime.utcnow() - timedelta(weeks=LOOKBACK_WEEKS)).isoformat(
            sep=" ", timespec="seconds"
        )

        try:
            cur = self.memory.conn.cursor()
            cur.execute(
                "SELECT id, timestamp FROM observations "
                "WHERE timestamp >= ? ORDER BY timestamp ASC",
                (cutoff,),
            )
            raw = cur.fetchall()
        except Exception:
            return []

        rows: list[dict] = []
        for obs_id, ts in raw:
            try:
                parsed = datetime.fromisoformat(ts)
            except (TypeError, ValueError):
                continue
            rows.append(
                {
                    "id": obs_id,
                    "timestamp": parsed,
                    "entities": self.memory.entities_for_observation(obs_id),
                }
            )
        return rows

    def _analyze_entity(
        self,
        entity_id: int,
        events: list[tuple[int, int, int]],
        meta: dict,
    ) -> Insight | None:
        # Group by weekday
        by_weekday: dict[int, list[tuple[int, int]]] = defaultdict(list)
        for weekday, hour, week in events:
            by_weekday[weekday].append((hour, week))

        # Find the strongest weekday+hour cluster
        best_pattern: dict | None = None
        for weekday, entries in by_weekday.items():
            hours = [h for h, _ in entries]

            if len(hours) < MIN_OCCURRENCES:
                continue

            # Find the tightest hour cluster
            hours.sort()
            best_cluster: list[int] = []
            for _i, h in enumerate(hours):
                cluster = [x for x in hours if abs(x - h) <= HOUR_TOLERANCE]
                if len(cluster) > len(best_cluster):
                    best_cluster = cluster

            if len(best_cluster) < MIN_OCCURRENCES:
                continue

            cluster_weeks = {w for h, w in entries if h in best_cluster}
            if len(cluster_weeks) < MIN_DISTINCT_WEEKS:
                continue

            cluster_hour = int(sum(best_cluster) / len(best_cluster))
            consistency = len(best_cluster) / len(hours)
            frequency = min(1.0, len(cluster_weeks) / LOOKBACK_WEEKS)
            score = round(0.5 * consistency + 0.5 * frequency, 2)

            candidate = {
                "weekday": weekday,
                "hour": cluster_hour,
                "occurrences": len(best_cluster),
                "weeks": len(cluster_weeks),
                "consistency": consistency,
                "frequency": frequency,
                "score": score,
            }
            if best_pattern is None or score > best_pattern["score"]:
                best_pattern = candidate

        if best_pattern is None:
            return None

        return self._build_insight(entity_id, meta, best_pattern)

    def _build_insight(self, entity_id: int, meta: dict, pattern: dict) -> Insight:
        weekday_name = (
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        )[pattern["weekday"]]
        hour = pattern["hour"]
        time_label = self._hour_label(hour)

        name = meta["name"]
        entity_type = meta["type"]

        return Insight(
            kind="recurring",
            title=f"Pattern: {name}",
            body=(
                f"You tend to engage with this {entity_type} on "
                f"{weekday_name} {time_label} "
                f"({pattern['occurrences']} times across "
                f"{pattern['weeks']} weeks)."
            ),
            score=pattern["score"],
            action="Show related activity",
            entity_id=entity_id,
        )

    @staticmethod
    def _week_index(when: datetime) -> int:
        """Return an integer identifying the ISO week."""
        iso = when.isocalendar()
        return iso[0] * 100 + iso[1]

    @staticmethod
    def _hour_label(hour: int) -> str:
        if hour < 6:
            return "late night"
        if hour < 9:
            return "early mornings"
        if hour < 12:
            return "mornings"
        if hour < 14:
            return "midday"
        if hour < 17:
            return "afternoons"
        if hour < 20:
            return "evenings"
        return "nights"
