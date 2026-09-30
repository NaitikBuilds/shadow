"""Session Memory — group observations into coherent work sessions.

A session is a run of observations that are close in time and share
at least one entity. Sessions can be listed, queried, and resumed.

No new tables. Sessions are computed on demand from observations.
"""

import hashlib
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

GAP_MIN = 15
MIN_OBSERVATIONS = 5
LOOKBACK_HOURS = 24


@dataclass
class Session:
    session_id: str
    start: datetime
    end: datetime
    duration_min: float
    observation_count: int
    primary_entity: tuple | None  # (type, name, id) or None
    preview: str

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "start": self.start.isoformat(sep=" ", timespec="seconds"),
            "end": self.end.isoformat(sep=" ", timespec="seconds"),
            "duration_min": round(self.duration_min, 1),
            "observation_count": self.observation_count,
            "primary_entity": (
                {
                    "type": self.primary_entity[0],
                    "name": self.primary_entity[1],
                    "id": self.primary_entity[2],
                }
                if self.primary_entity
                else None
            ),
            "preview": self.preview[:200],
        }


class SessionMemory:
    """Groups observations into work sessions and supports resume."""

    def __init__(self, memory):
        self.memory = memory

    def recent_sessions(
        self, hours: int = LOOKBACK_HOURS, limit: int = 10
    ) -> list[Session]:
        """Return recent sessions, most recent first."""
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat(
            sep=" ", timespec="seconds"
        )

        rows = self._load_rows(cutoff)
        if not rows:
            return []

        sessions: list[Session] = []
        current: list[dict] = []
        for row in rows:
            if not current:
                current.append(row)
                continue

            prev = current[-1]
            gap_min = (row["timestamp"] - prev["timestamp"]).total_seconds() / 60.0
            shared = bool(set(prev["entity_keys"]) & set(row["entity_keys"]))

            if gap_min <= GAP_MIN and shared:
                current.append(row)
            else:
                if len(current) >= MIN_OBSERVATIONS:
                    sessions.append(self._build_session(current))
                current = [row]

        if len(current) >= MIN_OBSERVATIONS:
            sessions.append(self._build_session(current))

        sessions.sort(key=lambda s: s.end, reverse=True)
        return sessions[:limit]

    def current_session(self) -> Session | None:
        """Return the session the user is currently in, if any."""
        sessions = self.recent_sessions(hours=2, limit=1)
        if not sessions:
            return None
        latest = sessions[0]
        # Only count as current if the session ended within the last GAP_MIN
        age_min = (datetime.utcnow() - latest.end).total_seconds() / 60.0
        if age_min <= GAP_MIN:
            return latest
        return None

    def resume_summary(self, session: Session) -> str:
        """Produce a short text summary for injecting into a query."""
        if session.primary_entity:
            name = session.primary_entity[1]
            return (
                f"Last session on {name}: "
                f"{session.observation_count} observations over "
                f"{int(session.duration_min)} minutes, ending "
                f"{self._humanize_ago(session.end)}."
            )
        return (
            f"Last session: {session.observation_count} observations over "
            f"{int(session.duration_min)} minutes, ending "
            f"{self._humanize_ago(session.end)}."
        )

    # ---------- internals ----------

    def _load_rows(self, cutoff: str) -> list[dict]:
        try:
            cur = self.memory.conn.cursor()
            cur.execute(
                "SELECT id, timestamp, source, content FROM observations "
                "WHERE timestamp >= ? ORDER BY timestamp ASC",
                (cutoff,),
            )
            raw = cur.fetchall()
        except Exception:
            return []

        rows: list[dict] = []
        for obs_id, ts, source, content in raw:
            try:
                parsed = datetime.fromisoformat(ts)
            except (TypeError, ValueError):
                continue
            entities = self.memory.entities_for_observation(obs_id)
            entity_keys = {
                (e["type"], e["name"])
                for e in entities
                if e["type"] in ("project", "file")
            }
            rows.append(
                {
                    "id": obs_id,
                    "timestamp": parsed,
                    "source": source,
                    "content": (content or "").strip(),
                    "entities": entities,
                    "entity_keys": entity_keys,
                }
            )
        return rows

    def _build_session(self, rows: list[dict]) -> Session:
        start = rows[0]["timestamp"]
        end = rows[-1]["timestamp"]
        duration_min = (end - start).total_seconds() / 60.0

        entity_counts: Counter = Counter()
        entity_ids: dict = {}
        for row in rows:
            for e in row["entities"]:
                if e["type"] in ("project", "file"):
                    key = (e["type"], e["name"])
                    entity_counts[key] += 1
                    entity_ids[key] = e["id"]

        primary: tuple | None = None
        if entity_counts:
            (etype, ename), _ = entity_counts.most_common(1)[0]
            primary = (etype, ename, entity_ids.get((etype, ename)))

        preview = rows[0]["content"] or ""
        sid = hashlib.sha1(
            f"{start.isoformat()}|{end.isoformat()}|{len(rows)}".encode()
        ).hexdigest()[:16]

        return Session(
            session_id=sid,
            start=start,
            end=end,
            duration_min=duration_min,
            observation_count=len(rows),
            primary_entity=primary,
            preview=preview,
        )

    @staticmethod
    def _humanize_ago(when: datetime) -> str:
        delta = datetime.utcnow() - when
        minutes = delta.total_seconds() / 60.0
        if minutes < 2:
            return "just now"
        if minutes < 60:
            return f"{int(minutes)} minutes ago"
        hours = minutes / 60.0
        if hours < 2:
            return "about an hour ago"
        return f"{int(hours)} hours ago"
