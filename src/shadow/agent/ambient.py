"""Ambient Task List — passive list of what you seem to be working on.

Derived from recent observations and entities. No manual input required.
Users can dismiss or promote items; those decisions persist in the
ambient_task_state table.
"""

import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class AmbientTask:
    entity_id: int
    entity_type: str
    name: str
    score: float
    mentions: int
    last_seen: datetime
    promoted: bool = False

    def to_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "name": self.name,
            "score": round(self.score, 3),
            "mentions": self.mentions,
            "last_seen": self.last_seen.isoformat(sep=" ", timespec="seconds"),
            "promoted": self.promoted,
        }


class AmbientTaskList:
    """Tracks the entities the user is currently engaging with."""

    LOOKBACK_HOURS = 24
    MAX_ITEMS = 10
    RECENCY_HALF_LIFE_HOURS = 24
    FULLY_FREQUENT_MENTIONS = 20
    SESSION_BOOST = 1.5

    def __init__(self, memory, session_memory=None):
        self.memory = memory
        self.session_memory = session_memory

    # ---------- public API ----------

    def list_active(self) -> list[AmbientTask]:
        """Return the current list of ambient tasks, highest score first."""
        cutoff = (datetime.utcnow() - timedelta(hours=self.LOOKBACK_HOURS)).isoformat(
            sep=" ", timespec="seconds"
        )

        rows = self._load_rows(cutoff)
        if not rows:
            return []

        state = self._load_state()
        current_entity_id = self._current_session_entity_id()

        counters: Counter = Counter()
        last_seen: dict = {}
        meta: dict = {}

        for row in rows:
            for e in row["entities"]:
                if e["type"] not in ("project", "file"):
                    continue
                key = e["id"]
                counters[key] += 1
                ts = row["timestamp"]
                if key not in last_seen or ts > last_seen[key]:
                    last_seen[key] = ts
                meta[key] = e

        now = datetime.utcnow()
        tasks: list[AmbientTask] = []
        for eid, mentions in counters.items():
            if state.get(eid) == "dismissed":
                continue

            hours_ago = (now - last_seen[eid]).total_seconds() / 3600.0
            recency = math.exp(-hours_ago / self.RECENCY_HALF_LIFE_HOURS)
            frequency = min(1.0, mentions / self.FULLY_FREQUENT_MENTIONS)
            score = 0.6 * recency + 0.4 * frequency

            if eid == current_entity_id:
                score = min(1.0, score * self.SESSION_BOOST)

            e = meta[eid]
            tasks.append(
                AmbientTask(
                    entity_id=eid,
                    entity_type=e["type"],
                    name=e["name"],
                    score=score,
                    mentions=mentions,
                    last_seen=last_seen[eid],
                    promoted=state.get(eid) == "promoted",
                )
            )

        tasks.sort(key=lambda t: t.score, reverse=True)
        return tasks[: self.MAX_ITEMS]

    def dismissed(self) -> list[AmbientTask]:
        """Return currently dismissed items (for the panel's 'Restore' list)."""
        state = self._load_state()
        dismissed_ids = [eid for eid, s in state.items() if s == "dismissed"]
        if not dismissed_ids:
            return []

        rows = self._load_rows_recent()
        meta: dict = {}
        last_seen: dict = {}
        mentions: Counter = Counter()
        for row in rows:
            for e in row["entities"]:
                if e["id"] in dismissed_ids:
                    meta[e["id"]] = e
                    last_seen[e["id"]] = max(
                        last_seen.get(e["id"], row["timestamp"]),
                        row["timestamp"],
                    )
                    mentions[e["id"]] += 1

        result = []
        for eid in dismissed_ids:
            if eid not in meta:
                continue
            e = meta[eid]
            result.append(
                AmbientTask(
                    entity_id=eid,
                    entity_type=e["type"],
                    name=e["name"],
                    score=0.0,
                    mentions=mentions.get(eid, 0),
                    last_seen=last_seen[eid],
                )
            )
        return result

    def dismiss(self, entity_id: int) -> None:
        self._set_state(entity_id, "dismissed")

    def promote(self, entity_id: int) -> None:
        self._set_state(entity_id, "promoted")

    def restore(self, entity_id: int) -> None:
        self._clear_state(entity_id)

    # ---------- internals ----------

    def _load_rows(self, cutoff: str) -> list[dict]:
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
        return self._rows_to_dicts(raw)

    def _load_rows_recent(self) -> list[dict]:
        cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat(
            sep=" ", timespec="seconds"
        )
        return self._load_rows(cutoff)

    def _rows_to_dicts(self, raw) -> list[dict]:
        result = []
        for obs_id, ts in raw:
            try:
                parsed = datetime.fromisoformat(ts)
            except (TypeError, ValueError):
                continue
            result.append(
                {
                    "id": obs_id,
                    "timestamp": parsed,
                    "entities": self.memory.entities_for_observation(obs_id),
                }
            )
        return result

    def _load_state(self) -> dict[int, str]:
        try:
            cur = self.memory.conn.cursor()
            cur.execute("SELECT entity_id, status FROM ambient_task_state")
            return {int(eid): s for eid, s in cur.fetchall()}
        except Exception:
            return {}

    def _set_state(self, entity_id: int, status: str) -> None:
        with self.memory._lock:
            cur = self.memory.conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO ambient_task_state "
                "(entity_id, status, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                (entity_id, status),
            )
            self.memory.conn.commit()

    def _clear_state(self, entity_id: int) -> None:
        with self.memory._lock:
            cur = self.memory.conn.cursor()
            cur.execute(
                "DELETE FROM ambient_task_state WHERE entity_id = ?",
                (entity_id,),
            )
            self.memory.conn.commit()

    def _current_session_entity_id(self) -> int | None:
        if self.session_memory is None:
            return None
        try:
            session = self.session_memory.current_session()
            if session and session.primary_entity:
                return session.primary_entity[2]
        except Exception:
            pass
        return None
