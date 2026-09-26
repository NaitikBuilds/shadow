from datetime import datetime, timedelta


class ShadowRetriever:
    """Combines semantic and temporal retrieval from the MemoryStore."""

    def __init__(self, memory, backend):
        self.memory = memory
        self.backend = backend

    def semantic(self, query: str, k: int = 5) -> list[dict]:
        try:
            vec = self.backend.embed(query)
        except RuntimeError:
            return []
        rows = self.memory.search_similar(vec, limit=k)
        return [
            {
                "id": r[0],
                "content": r[1],
                "timestamp": r[2],
                "source": r[3],
                "distance": r[4],
            }
            for r in rows
        ]

    def temporal(self, window: str) -> list[dict]:
        now = datetime.utcnow()
        start = _window_start(now, window)
        if start is None:
            return []
        rows = self.memory.observations_between(
            start.isoformat(sep=" ", timespec="seconds"),
            now.isoformat(sep=" ", timespec="seconds"),
        )
        return [
            {"id": r[0], "timestamp": r[1], "source": r[2], "content": r[3]}
            for r in rows
        ]

    def context_for(self, query: str, k: int = 5) -> str:
        """Build a small context block for the LLM from retrieved observations."""
        pieces = []
        for obs in self.semantic(query, k=k):
            pieces.append(f"- [{obs['timestamp']}] ({obs['source']}) {obs['content']}")
        if not pieces:
            return ""
        return "Relevant past observations:\n" + "\n".join(pieces)


def _window_start(now: datetime, window: str) -> datetime | None:
    w = window.lower().strip()
    if w in ("today",):
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if w in ("yesterday",):
        d = now - timedelta(days=1)
        return d.replace(hour=0, minute=0, second=0, microsecond=0)
    if w in ("last week", "this week"):
        return now - timedelta(days=7)
    if w in ("last month", "this month"):
        return now - timedelta(days=30)
    return None
