"""Ethical Mirror values store (C07).

Backed by `ethical_values` and `ethical_values_history` (migration 008).

Design (per PRD §22.4.2 / §22.6.1):
  - Every value is user-stated: source='user_stated' CHECK enforced by schema.
  - Values are advisory only. This module does not generate reflections
    (that's C09) or run onboarding (that's C08).
  - Limited mode = fewer than 10 active values; the flag is exposed so
    callers can warn without re-checking the count.
  - Wipe integration: register_phase4_handlers already covers these tables
    (conditional on migration 008 having run).
  - Retention: ethical values are never pruned (register_phase4_defaults
    registers them with days=None).
"""

from __future__ import annotations

import time

LOW_VALUE_MIN_CHARS = 1
HIGH_VALUE_MAX_CHARS = 300
COMPLETE_PROFILE_MIN = 10


class EthicalValueValidationError(ValueError):
    """Raised for empty, overlong, or non-string input."""


class EthicalValueDuplicateError(EthicalValueValidationError):
    """Raised when an active value with the same normalized text already exists."""


class EthicalValueNotFoundError(KeyError):
    """Raised when a value_id cannot be found."""


def _now_ms() -> int:
    return int(time.time() * 1000)


def _normalize(text: str) -> str:
    """Normalize for duplicate detection. ASCII case-fold only (SQLite parity)."""
    return " ".join(text.strip().lower().split())


def _coerce_text(text) -> str:
    if not isinstance(text, str):
        raise EthicalValueValidationError(
            f"value text must be str, got {type(text).__name__}"
        )
    stripped = text.strip()
    if len(stripped) < LOW_VALUE_MIN_CHARS:
        raise EthicalValueValidationError("value text is empty")
    if len(stripped) > HIGH_VALUE_MAX_CHARS:
        raise EthicalValueValidationError(
            f"value text exceeds {HIGH_VALUE_MAX_CHARS} characters"
        )
    return stripped


class EthicalValuesStore:
    """CRUD around the ethical_values table. Single-tenant, local only."""

    def __init__(self, memory) -> None:
        # `memory` is a MemoryStore — we reuse its connection.
        self._memory = memory
        self._conn = memory.conn

    # ---- create ----------------------------------------------------------
    def add(
        self,
        text: str,
        *,
        label: str | None = None,
        onboarding_prompt_id: int | None = None,
    ) -> int:
        """Insert a new active value. Returns value_id.

        Raises:
          EthicalValueValidationError — empty/overlong/non-str input
          EthicalValueDuplicateError  — same normalized text is already active
        """
        clean = _coerce_text(text)
        now = _now_ms()

        with self._conn:
            # Application-layer duplicate check (parity with the UNIQUE
            # partial index, but catches non-ASCII cases the index can't).
            existing = self._conn.execute(
                "SELECT value_id FROM ethical_values "
                "WHERE status = 'active' AND lower(trim(text)) = ?",
                (_normalize(clean),),
            ).fetchone()
            if existing is not None:
                raise EthicalValueDuplicateError(
                    f"an active value with the same text already exists "
                    f"(value_id={existing[0]})"
                )

            # Append at end of the active ordering.
            max_pos_row = self._conn.execute(
                "SELECT COALESCE(MAX(position), -1) FROM ethical_values "
                "WHERE status = 'active'"
            ).fetchone()
            next_pos = int(max_pos_row[0]) + 1

            cur = self._conn.execute(
                "INSERT INTO ethical_values"
                "(text, label, position, status, source, "
                " onboarding_prompt_id, version, created_at, updated_at) "
                "VALUES (?, ?, ?, 'active', 'user_stated', ?, 1, ?, ?)",
                (clean, label, next_pos, onboarding_prompt_id, now, now),
            )
            return cur.lastrowid

    # ---- update ----------------------------------------------------------
    def update(
        self,
        value_id: int,
        *,
        text: str | None = None,
        label: str | None = None,
    ) -> bool:
        """Update text and/or label. Records history when text changes."""
        current = self.get(value_id)
        if current is None:
            raise EthicalValueNotFoundError(value_id)
        if text is None and label is None:
            return False

        new_text = current["text"] if text is None else _coerce_text(text)
        new_label = current["label"] if label is None else label

        if new_text == current["text"] and new_label == current["label"]:
            return False

        if new_text != current["text"]:
            dup = self._conn.execute(
                "SELECT value_id FROM ethical_values "
                "WHERE status = 'active' AND value_id != ? "
                "AND lower(trim(text)) = ?",
                (value_id, _normalize(new_text)),
            ).fetchone()
            if dup is not None:
                raise EthicalValueDuplicateError(
                    f"an active value with the same text already exists "
                    f"(value_id={dup[0]})"
                )

        now = _now_ms()
        with self._conn:
            if new_text != current["text"]:
                self._conn.execute(
                    "INSERT INTO ethical_values_history"
                    "(value_id, old_text, old_label, change_type, changed_at) "
                    "VALUES (?, ?, ?, 'update', ?)",
                    (value_id, current["text"], current["label"], now),
                )
            self._conn.execute(
                "UPDATE ethical_values "
                "SET text = ?, label = ?, version = version + 1, updated_at = ? "
                "WHERE value_id = ?",
                (new_text, new_label, now, value_id),
            )
        return True

    # ---- delete / archive ------------------------------------------------
    def delete(self, value_id: int) -> bool:
        """Hard delete. Cascades to history."""
        with self._conn:
            cur = self._conn.execute(
                "DELETE FROM ethical_values WHERE value_id = ?", (value_id,)
            )
        return (cur.rowcount or 0) > 0

    def archive(self, value_id: int) -> bool:
        """Mark inactive; excluded from list_active/count_active."""
        current = self.get(value_id)
        if current is None:
            raise EthicalValueNotFoundError(value_id)
        if current["status"] == "archived":
            return False
        now = _now_ms()
        with self._conn:
            self._conn.execute(
                "INSERT INTO ethical_values_history"
                "(value_id, old_text, old_label, change_type, changed_at) "
                "VALUES (?, ?, ?, 'archive', ?)",
                (value_id, current["text"], current["label"], now),
            )
            self._conn.execute(
                "UPDATE ethical_values SET status = 'archived', updated_at = ? "
                "WHERE value_id = ?",
                (now, value_id),
            )
        return True

    def restore(self, value_id: int) -> bool:
        current = self.get(value_id)
        if current is None:
            raise EthicalValueNotFoundError(value_id)
        if current["status"] == "active":
            return False
        now = _now_ms()
        with self._conn:
            self._conn.execute(
                "INSERT INTO ethical_values_history"
                "(value_id, old_text, old_label, change_type, changed_at) "
                "VALUES (?, ?, ?, 'restore', ?)",
                (value_id, current["text"], current["label"], now),
            )
            self._conn.execute(
                "UPDATE ethical_values SET status = 'active', updated_at = ? "
                "WHERE value_id = ?",
                (now, value_id),
            )
        return True

    # ---- reorder ---------------------------------------------------------
    def reorder(self, value_ids: list[int]) -> None:
        """Rewrite positions in the given order. Ignores unknown/archived ids."""
        if not value_ids:
            return
        now = _now_ms()
        with self._conn:
            for pos, vid in enumerate(value_ids):
                self._conn.execute(
                    "UPDATE ethical_values SET position = ?, updated_at = ? "
                    "WHERE value_id = ? AND status = 'active'",
                    (pos, now, vid),
                )

    # ---- read ------------------------------------------------------------
    def get(self, value_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT value_id, text, label, position, status, source, "
            "onboarding_prompt_id, version, created_at, updated_at "
            "FROM ethical_values WHERE value_id = ?",
            (value_id,),
        ).fetchone()
        return _row_to_dict(row) if row else None

    def list_active(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT value_id, text, label, position, status, source, "
            "onboarding_prompt_id, version, created_at, updated_at "
            "FROM ethical_values WHERE status = 'active' "
            "ORDER BY position ASC, value_id ASC"
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def list_archived(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT value_id, text, label, position, status, source, "
            "onboarding_prompt_id, version, created_at, updated_at "
            "FROM ethical_values WHERE status = 'archived' "
            "ORDER BY updated_at DESC"
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def count_active(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM ethical_values WHERE status = 'active'"
        ).fetchone()
        return int(row[0])

    def is_limited_mode(self) -> bool:
        """True when fewer than COMPLETE_PROFILE_MIN active values exist."""
        return self.count_active() < COMPLETE_PROFILE_MIN

    # ---- destructive -----------------------------------------------------
    def clear_all(self) -> int:
        """User-triggered 'delete all values'. Removes rows and history."""
        with self._conn:
            cur = self._conn.execute("DELETE FROM ethical_values")
        return cur.rowcount or 0

    # ---- onboarding state ------------------------------------------------
    def is_opted_out(self) -> bool:
        return self._memory.get_meta(_OPT_OUT_META_KEY) == "1"

    def set_opt_out(self, opted_out: bool) -> None:
        self._memory.set_meta(_OPT_OUT_META_KEY, "1" if opted_out else "0")

    def is_onboarded(self) -> bool:
        return bool(self._memory.get_meta(_ONBOARDED_META_KEY))

    def mark_onboarded(self) -> None:
        self._memory.set_meta(_ONBOARDED_META_KEY, str(_now_ms()))

    def reset_onboarding(self) -> None:
        self._memory.set_meta(_ONBOARDED_META_KEY, "")
        self._memory.set_meta(_DISMISSED_META_KEY, "0")

    def dismissed_count(self) -> int:
        raw = self._memory.get_meta(_DISMISSED_META_KEY) or "0"
        try:
            return int(raw)
        except ValueError:
            return 0

    def increment_dismissed(self) -> int:
        n = self.dismissed_count() + 1
        self._memory.set_meta(_DISMISSED_META_KEY, str(n))
        return n

    def should_offer_onboarding(self) -> bool:
        """Whether to show the first-run wizard at app launch."""
        if self.is_opted_out():
            return False
        if self.is_onboarded():
            return False
        return self.dismissed_count() < DISMISS_OFFER_LIMIT


def _row_to_dict(row) -> dict:
    return {
        "value_id": row[0],
        "text": row[1],
        "label": row[2],
        "position": row[3],
        "status": row[4],
        "source": row[5],
        "onboarding_prompt_id": row[6],
        "version": row[7],
        "created_at": row[8],
        "updated_at": row[9],
    }


# ---------------------------------------------------------------------------
# Onboarding prompts + first-run helpers (C08)
# ---------------------------------------------------------------------------
# Ten non-diagnostic prompts (per FR-P4-ETH-06: no health / politics / religion).
# Order matters: it is the display order and the onboarding_prompt_id value.
ONBOARDING_PROMPTS: tuple[str, ...] = (
    "What do you value most in how you treat other people?",
    "What is a principle you would never compromise, even under pressure?",
    "When you must choose between speed and thoroughness, what guides you?",
    "What does 'integrity' mean in your work?",
    "What kind of impact do you want your work to have?",
    "How do you weigh short-term wins against long-term consequences?",
    "What would make you say no to an opportunity, even if it paid well?",
    "When you disagree with someone, what matters more — being heard, "
    "or understanding them?",
    "What mistake have you made that taught you something you still live by?",
    "If someone described your values in one sentence, what would you hope "
    "they would say?",
)

_OPT_OUT_META_KEY = "ethical_mirror_opt_out"
_ONBOARDED_META_KEY = "ethical_mirror_onboarded_at"
_DISMISSED_META_KEY = "ethical_mirror_dismissed_count"

DISMISS_OFFER_LIMIT = 3


def next_unanswered_prompt_index(store: EthicalValuesStore) -> int | None:
    """Return the index (0..N-1) of the first ONBOARDING_PROMPTS not yet
    answered by an active value, or None if all are answered."""
    answered = {
        v["onboarding_prompt_id"]
        for v in store.list_active()
        if v["onboarding_prompt_id"] is not None
    }
    for i in range(len(ONBOARDING_PROMPTS)):
        if i not in answered:
            return i
    return None


def answered_prompt_count(store: EthicalValuesStore) -> int:
    """Number of ONBOARDING_PROMPTS covered by an active value."""
    answered = {
        v["onboarding_prompt_id"]
        for v in store.list_active()
        if v["onboarding_prompt_id"] is not None
    }
    return sum(1 for i in range(len(ONBOARDING_PROMPTS)) if i in answered)
