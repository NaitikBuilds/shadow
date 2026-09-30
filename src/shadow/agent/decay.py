"""Knowledge Decay Detection — surface entities you used to engage with.

Looks at the entities table for entries that were mentioned frequently
in the past but haven't appeared recently. Produces gentle insights,
never urgent notifications.
"""

from datetime import datetime, timedelta

from .insight import Insight


class KnowledgeDecayEngine:
    """Finds entities that are fading from the user's working memory."""

    MIN_MENTIONS = 5
    MIN_STALE_DAYS = 14
    FULLY_IMPORTANT_MENTIONS = 20
    FULLY_STALE_DAYS = 30

    def __init__(self, memory):
        self.memory = memory

    def find_decaying(self, limit: int = 3) -> list[Insight]:
        now = datetime.utcnow()
        cutoff = (now - timedelta(days=self.MIN_STALE_DAYS)).isoformat(
            sep=" ", timespec="seconds"
        )

        try:
            cur = self.memory.conn.cursor()
            cur.execute(
                "SELECT id, type, name, mention_count, last_seen "
                "FROM entities "
                "WHERE type IN ('project', 'file') "
                "AND mention_count >= ? "
                "AND last_seen < ? "
                "ORDER BY mention_count DESC LIMIT 50",
                (self.MIN_MENTIONS, cutoff),
            )
            rows = cur.fetchall()
        except Exception:
            return []

        insights: list[Insight] = []
        for eid, etype, name, mentions, last_seen in rows:
            try:
                last_dt = datetime.fromisoformat(last_seen)
            except (TypeError, ValueError):
                continue

            days_since = (now - last_dt).total_seconds() / 86400.0
            importance = min(1.0, mentions / self.FULLY_IMPORTANT_MENTIONS)
            staleness = min(1.0, days_since / self.FULLY_STALE_DAYS)
            score = round(0.5 * importance + 0.5 * staleness, 2)

            if days_since < self.MIN_STALE_DAYS:
                continue

            insights.append(
                self._make_insight(eid, etype, name, mentions, days_since, score)
            )

            if len(insights) >= limit:
                break

        insights.sort(key=lambda i: i.score, reverse=True)
        return insights[:limit]

    def _make_insight(
        self,
        entity_id: int,
        entity_type: str,
        name: str,
        mentions: int,
        days_since: float,
        score: float,
    ) -> Insight:
        if days_since < 30:
            ago = f"{int(days_since)} days"
        elif days_since < 60:
            ago = "a few weeks"
        else:
            months = int(days_since / 30)
            ago = f"{months} months"

        kind_label = "file" if entity_type == "file" else "project"

        return Insight(
            kind="decay",
            title=f"Fading: {name}",
            body=(
                f"You used to work on this {kind_label} regularly "
                f"({mentions} mentions), but haven't touched it in {ago}."
            ),
            score=score,
            action="Take a look",
            entity_id=entity_id,
        )
