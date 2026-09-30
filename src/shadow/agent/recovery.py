from collections import defaultdict
from datetime import datetime, timedelta

from .insight import Insight


class RecoveryEngine:
    """Finds work the user was doing but hasn't returned to.

    Heuristic:
      1. Pull observations from the last N hours.
      2. Group by primary entity (project > file > topic).
      3. A group is "unfinished" if it had meaningful activity,
         spanned at least MIN_DURATION_MIN, ended at least GAP_MIN
         ago, and the user hasn't returned in the last
         RECENT_RETURN_MIN minutes.
      4. Score = 0.6 * recency + 0.4 * duration.
    """

    MIN_OBSERVATIONS = 4
    MIN_DURATION_MIN = 8
    GAP_MIN = 25
    RECENT_RETURN_MIN = 5

    def __init__(self, memory):
        self.memory = memory

    def find_unfinished(self, hours: int = 24, limit: int = 5) -> list[Insight]:
        now = datetime.now()
        rows = self._recent_observations(now - timedelta(hours=hours))
        if not rows:
            return []

        groups = self._group_by_primary_entity(rows)
        insights: list[Insight] = []
        for key, obs_list in groups.items():
            insight = self._evaluate_group(key, obs_list, now)
            if insight is not None:
                insights.append(insight)

        insights.sort(key=lambda i: i.score, reverse=True)
        return insights[:limit]

    # ---------- internals ----------

    def _recent_observations(self, since: datetime) -> list[dict]:
        cur = self.memory.conn.cursor()
        cur.execute(
            "SELECT id, timestamp, source, content FROM observations "
            "WHERE timestamp >= ? ORDER BY timestamp ASC",
            (since.isoformat(sep=" ", timespec="seconds"),),
        )
        result = []
        for obs_id, ts, source, content in cur.fetchall():
            try:
                parsed = datetime.fromisoformat(ts)
            except (TypeError, ValueError):
                continue
            result.append(
                {
                    "id": obs_id,
                    "timestamp": parsed,
                    "source": source,
                    "content": content or "",
                    "entities": self.memory.entities_for_observation(obs_id),
                }
            )
        return result

    def _group_by_primary_entity(self, rows: list[dict]) -> dict:
        groups: dict[tuple, list[dict]] = defaultdict(list)
        for row in rows:
            entity = self._pick_primary_entity(row["entities"])
            if entity is None:
                continue
            key = (entity["type"], entity["name"], entity["id"])
            groups[key].append(row)
        return groups

    @staticmethod
    def _pick_primary_entity(entities: list[dict]) -> dict | None:
        if not entities:
            return None
        for pref in ("project", "file", "topic"):
            for e in entities:
                if e["type"] == pref:
                    return e
        return entities[0]

    def _evaluate_group(
        self, key: tuple, obs_list: list[dict], now: datetime
    ) -> Insight | None:
        entity_type, entity_name, entity_id = key

        if len(obs_list) < self.MIN_OBSERVATIONS:
            return None

        first = obs_list[0]["timestamp"]
        last = obs_list[-1]["timestamp"]
        duration_min = (last - first).total_seconds() / 60.0
        if duration_min < self.MIN_DURATION_MIN:
            return None

        gap_since_last = (now - last).total_seconds() / 60.0
        if gap_since_last < self.GAP_MIN:
            return None

        recent_cutoff = now - timedelta(minutes=self.RECENT_RETURN_MIN)
        if any(row["timestamp"] >= recent_cutoff for row in obs_list):
            return None

        title = f"Unfinished: {entity_name}"
        body = (
            f"You worked on {entity_name} for about "
            f"{self._humanize(duration_min)} and last touched it "
            f"{self._humanize(gap_since_last)} ago."
        )

        recency = max(0.0, 1.0 - gap_since_last / (24 * 60))
        length = min(1.0, duration_min / 60.0)
        score = round(0.6 * recency + 0.4 * length, 2)

        return Insight(
            kind="recovery",
            title=title,
            body=body,
            score=score,
            action="Resume where you left off",
            entity_id=entity_id,
        )

    @staticmethod
    def _humanize(minutes: float) -> str:
        if minutes < 60:
            return f"{int(minutes)} minutes"
        hours = minutes / 60.0
        if hours < 2:
            return "about an hour"
        return f"{int(hours)} hours"
