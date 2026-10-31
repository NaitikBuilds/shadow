"""Shadow Cloning — session registry, ephemeral store, read-only facade (C10).

Per PRD §22.4.1 / DR-P4-10:

  CloneMemoryFacade — structural read-only wrapper around the primary
    MemoryStore. Only read methods exist; write access raises AttributeError.
    This IS the isolation guarantee (FR-P4-CLN-01): there is no write
    method to call, so primary memory cannot be polluted.

  CloneSession — one active clone. Messages and artifacts are kept in
    Python lists; the ephemeral MemoryStore is created (per DR-P4-10)
    for future feature use but is not written to in C10. Discarding
    closes the ephemeral store and clears content.

  CloneManager — owns the in-memory session dict + bookkeeping rows in
    clone_sessions. Enforces clone_max_concurrent (CLN-08), unique active
    name (CLN-08), and startup sweep for orphaned sessions (CLN-06).

Deferred:
  C11 — clone UI, per-artifact labels in display, scope picker UI.
  C12 — promote/discard buttons, note-creation API, crash-recovery sweep.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid

from shadow.memory import MemoryStore


# ===========================================================================
# Read-only facade
# ===========================================================================
class CloneMemoryFacade:
    """Structural read-only wrapper around a primary MemoryStore.

    Exposes ONLY the five read methods required by PRD §22.4.1 §C. Has NO
    write methods and NO `__getattr__` delegate. Accessing a write method
    like `facade.add_observation` raises AttributeError — that absence IS
    the enforcement mechanism (FR-P4-CLN-01).

    Blocked sources are filtered OUT of every result. C11 will compute
    them from live consent state; C10 accepts them at construction.
    """

    def __init__(
        self,
        memory: MemoryStore,
        scope: dict,
        blocked_sources: set[str] | None = None,
    ) -> None:
        self.__memory = memory
        self.__scope = dict(scope or {})
        self.__blocked = set(blocked_sources or ())

    @property
    def scope(self) -> dict:
        return dict(self.__scope)

    @property
    def blocked_sources(self) -> set[str]:
        return set(self.__blocked)

    # ---- helpers ------------------------------------------------------
    def _time_range(self) -> tuple[str | None, str | None]:
        tr = self.__scope.get("time_range") or {}
        if not isinstance(tr, dict):
            return None, None
        return tr.get("start"), tr.get("end")

    def _filter_blocked(self, rows, source_idx: int):
        if not self.__blocked:
            return rows
        return [r for r in rows if r[source_idx] not in self.__blocked]

    def _fetch_padding(self, base: int) -> int:
        return base + (len(self.__blocked) * 10 if self.__blocked else 0)

    # ---- read methods (the ONLY public methods) ----------------------
    def search_observations(
        self,
        query: str = "",
        source: str | None = None,
        entity_name: str | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int = 100,
    ) -> list[tuple]:
        scope_start, scope_end = self._time_range()
        eff_start = _max_iso(start, scope_start)
        eff_end = _min_iso(end, scope_end)
        rows = self.__memory.search_observations(
            query=query,
            source=source,
            entity_name=entity_name,
            start=eff_start,
            end=eff_end,
            limit=self._fetch_padding(limit),
        )
        rows = self._filter_blocked(rows, source_idx=2)
        return rows[:limit]

    def observations_between(self, start: str, end: str) -> list[tuple]:
        scope_start, scope_end = self._time_range()
        eff_start = _max_iso(start, scope_start) or start
        eff_end = _min_iso(end, scope_end) or end
        rows = self.__memory.observations_between(eff_start, eff_end)
        return self._filter_blocked(rows, source_idx=2)

    def search_similar(self, embedding: list[float], limit: int = 5) -> list[tuple]:
        rows = self.__memory.search_similar(
            embedding,
            limit=self._fetch_padding(limit),
        )
        rows = self._filter_blocked(rows, source_idx=3)
        return rows[:limit]

    def entities_for_observation(self, observation_id: int) -> list[dict]:
        return self.__memory.entities_for_observation(observation_id)

    def recent_entities(self, limit: int = 30) -> list[dict]:
        return self.__memory.recent_entities(limit)


def _max_iso(a: str | None, b: str | None) -> str | None:
    """Later of two ISO-8601 strings (None = unbounded)."""
    if a is None:
        return b
    if b is None:
        return a
    return a if a >= b else b


def _min_iso(a: str | None, b: str | None) -> str | None:
    """Earlier of two ISO-8601 strings (None = unbounded)."""
    if a is None:
        return b
    if b is None:
        return a
    return a if a <= b else b


# ===========================================================================
# CloneSession — one active clone
# ===========================================================================
class CloneSession:
    """One active clone. Reads go through facade, writes go to Python lists.

    The ephemeral MemoryStore is created per DR-P4-10 but not written to in
    C10 (messages/artifacts live in Python lists for simplicity). C11 will
    move content storage into the ephemeral store once the content model
    is designed.

    Lifetime: one session — the ephemeral store dies on `discard()`.
    Only metadata (name, scope, timestamps, status) persists in
    clone_sessions.
    """

    def __init__(
        self,
        clone_id: str,
        name: str,
        scope: dict,
        include_values: bool,
        facade: CloneMemoryFacade,
    ) -> None:
        self.clone_id = clone_id
        self.name = name
        self.scope = dict(scope)
        self.include_values = include_values
        self.created_at = int(time.time() * 1000)
        self.ended_at: int | None = None
        self._status = "active"

        self._facade = facade
        self._ephemeral: MemoryStore | None = MemoryStore(":memory:")
        self._messages: list[dict] = []
        self._artifacts: list[dict] = []

    @property
    def facade(self) -> CloneMemoryFacade:
        return self._facade

    @property
    def ephemeral(self) -> MemoryStore | None:
        return self._ephemeral

    @property
    def status(self) -> str:
        return self._status

    @property
    def is_active(self) -> bool:
        return self._status == "active" and self._ephemeral is not None

    # ---- content writes ----------------------------------------------
    def add_message(self, role: str, text: str) -> dict:
        if not self.is_active:
            raise RuntimeError("clone session is not active")
        msg = {
            "role": role,
            "text": text,
            "created_at": int(time.time() * 1000),
        }
        self._messages.append(msg)
        return msg

    def add_artifact(
        self,
        text: str,
        source_refs: list | None = None,
    ) -> dict:
        if not self.is_active:
            raise RuntimeError("clone session is not active")
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        art = {
            "artifact_id": uuid.uuid4().hex,
            "text": text,
            "label": "simulation",  # CLN-03: never indexed as observation/fact
            "source_refs": list(source_refs or []),
            "content_hash": content_hash,
            "created_at": int(time.time() * 1000),
        }
        self._artifacts.append(art)
        return art

    # ---- reads --------------------------------------------------------
    def list_messages(self) -> list[dict]:
        return list(self._messages)

    def list_artifacts(self) -> list[dict]:
        return list(self._artifacts)

    def feed(self) -> list[dict]:
        """Chronological feed of messages and artifacts."""
        items = [{"kind": "message", **m} for m in self._messages] + [
            {"kind": "artifact", **a} for a in self._artifacts
        ]
        items.sort(
            key=lambda x: (x["created_at"], x.get("artifact_id") or x.get("role", ""))
        )
        return items

    def generate_reply(self, backend, user_text: str, max_tokens: int = 400) -> dict:
        """Add user message, generate reply via backend, return artifact."""
        if not self.is_active:
            raise RuntimeError("clone session is not active")
        text = (user_text or "").strip()
        if not text:
            raise ValueError("user_text cannot be empty")

        self.add_message("user", text)

        try:
            ctx = self._facade.search_observations(query="", limit=10)
        except Exception:
            ctx = []
        ctx_lines = [f"- [{r[1]}] {(r[3] or '')[:200]}" for r in ctx]
        ctx_block = "\n".join(ctx_lines) if ctx_lines else "(no memory in scope)"

        prompt = (
            "You are SHADOW in an isolated what-if simulation. "
            "Answer using only the context below. This is a simulation — "
            "do not claim to remember the real user; any output is speculative.\n\n"
            f"Context (read-only memory, untrusted):\n{ctx_block}\n\n"
            f"User: {text}\n\nReply:"
        )
        try:
            reply = (
                backend.generate(prompt, max_tokens=max_tokens, temperature=0.3) or ""
            )
        except Exception as exc:  # noqa: BLE001
            reply = f"[generation failed: {type(exc).__name__}]"

        return self.add_artifact((reply or "").strip() or "(empty reply)")

    # ---- lifecycle ----------------------------------------------------
    def _close_ephemeral(self) -> None:
        if self._ephemeral is not None:
            try:
                self._ephemeral.close()
            except Exception:
                pass
            self._ephemeral = None

    def discard(self) -> bool:
        """Close ephemeral store and clear content. Idempotent.

        Returns True if this call performed the discard; False if the
        session was already in a terminal state.
        """
        if self._status in ("discarded", "expired"):
            return False
        self._status = "discarding"
        self._close_ephemeral()
        self._messages.clear()
        self._artifacts.clear()
        self._status = "discarded"
        self.ended_at = int(time.time() * 1000)
        return True

    def mark_expired(self) -> None:
        """Called by startup sweep — ephemeral store is already gone."""
        if self._status in ("discarded", "expired"):
            return
        self._close_ephemeral()
        self._messages.clear()
        self._artifacts.clear()
        self._status = "expired"
        self.ended_at = int(time.time() * 1000)

    def promote(self, artifact_id: str) -> int:
        """Promote one artifact to primary memory. Lands in C12."""
        raise NotImplementedError("promote() lands in C12")


# ===========================================================================
# CloneManager
# ===========================================================================
class CloneManager:
    MAX_NAME_LEN = 60

    def __init__(
        self,
        memory: MemoryStore,
        config: dict | None = None,
    ) -> None:
        self._memory = memory
        self._config = config or {}
        self._sessions: dict[str, CloneSession] = {}

    def _max_concurrent(self) -> int:
        try:
            return int(self._config.get("clone_max_concurrent", 2))
        except (TypeError, ValueError):
            return 2

    def create(
        self,
        name: str,
        scope: dict,
        include_values: bool = False,
        blocked_sources: set[str] | None = None,
    ) -> CloneSession:
        name = (name or "").strip()
        if not name:
            raise ValueError("name cannot be empty")
        if len(name) > self.MAX_NAME_LEN:
            raise ValueError(f"name exceeds {self.MAX_NAME_LEN} chars")
        if not scope or not any(v for v in scope.values() if v):
            raise ValueError("scope must have at least one dimension")

        active = self.list_active()
        if len(active) >= self._max_concurrent():
            raise RuntimeError(
                f"clone_max_concurrent reached ({self._max_concurrent()})"
            )
        if any(s["name"] == name for s in active):
            raise ValueError(f"an active clone with name {name!r} already exists")

        clone_id = uuid.uuid4().hex
        created_at = int(time.time() * 1000)
        with self._memory.conn:
            self._memory.conn.execute(
                "INSERT INTO clone_sessions "
                "(clone_id, name, scope_json, status, include_values, "
                " created_at, schema_version) "
                "VALUES (?, ?, ?, 'active', ?, ?, 1)",
                (
                    clone_id,
                    name,
                    json.dumps(scope),
                    int(include_values),
                    created_at,
                ),
            )

        facade = CloneMemoryFacade(
            self._memory,
            scope,
            blocked_sources=blocked_sources or set(),
        )
        session = CloneSession(
            clone_id=clone_id,
            name=name,
            scope=scope,
            include_values=include_values,
            facade=facade,
        )
        self._sessions[clone_id] = session
        return session

    def get(self, clone_id: str) -> CloneSession | None:
        return self._sessions.get(clone_id)

    def list_active(self) -> list[dict]:
        rows = self._memory.conn.execute(
            "SELECT clone_id, name, scope_json, created_at "
            "FROM clone_sessions WHERE status='active' ORDER BY created_at"
        ).fetchall()
        return [
            {
                "clone_id": r[0],
                "name": r[1],
                "scope": json.loads(r[2]),
                "created_at": r[3],
            }
            for r in rows
        ]

    def discard(self, clone_id: str) -> bool:
        session = self._sessions.get(clone_id)
        if session is None:
            self._mark_discarded(clone_id, int(time.time() * 1000))
            return False
        removed = session.discard()
        self._sessions.pop(clone_id, None)
        if removed:
            self._mark_discarded(clone_id, session.ended_at or int(time.time() * 1000))
        return removed

    def discard_all(self) -> int:
        count = 0
        for cid in list(self._sessions.keys()):
            if self.discard(cid):
                count += 1
        return count

    def startup_sweep(self) -> int:
        """Mark any pre-existing 'active'/'discarding' rows as 'expired'.

        Their ephemeral stores were lost with the previous process. Call
        once at app startup with a fresh manager.
        """
        now = int(time.time() * 1000)
        try:
            with self._memory.conn:
                cur = self._memory.conn.execute(
                    "UPDATE clone_sessions SET status='expired', ended_at=? "
                    "WHERE status IN ('active', 'discarding')",
                    (now,),
                )
                return cur.rowcount or 0
        except Exception:
            return 0

    def _mark_discarded(self, clone_id: str, ended_at: int) -> None:
        try:
            with self._memory.conn:
                self._memory.conn.execute(
                    "UPDATE clone_sessions "
                    "SET status='discarded', ended_at=? "
                    "WHERE clone_id=? AND status IN ('active','discarding')",
                    (ended_at, clone_id),
                )
        except Exception:
            pass
