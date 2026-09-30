"""Contextual Focus Shield — suppress non-critical insights during deep work.

Reads the recent focus signal from typing_dynamics observations and
exposes a filter that the Insight panel consults. Never modifies memory,
never changes what's observed. Display-only.
"""

from datetime import datetime, timedelta
from enum import StrEnum

from .insight import Insight


class FocusState(StrEnum):
    FOCUSED = "focused"
    NORMAL = "normal"
    IDLE = "idle"


# Weighted focus score threshold to consider the user "focused".
FOCUSED_THRESHOLD = 0.65

# Window in which we look at recent typing_dynamics observations.
FOCUS_WINDOW_MIN = 10
IDLE_WINDOW_MIN = 15

# Minimum insight score surfaced while focused.
FOCUSED_MIN_SCORE = 0.85


class FocusShield:
    """Classifies the current focus state and filters insights accordingly."""

    def __init__(self, memory):
        self.memory = memory

    # ---------- public API ----------

    def current_state(self) -> FocusState:
        """Classify the current state from recent typing_dynamics rows."""
        rows = self._recent_typing_rows()
        if not rows:
            return FocusState.NORMAL

        now = datetime.utcnow()
        latest = rows[-1]["timestamp"]

        # No typing in the idle window → idle.
        if (now - latest) > timedelta(minutes=IDLE_WINDOW_MIN):
            return FocusState.IDLE

        # Focused if recent observations have a high weighted focus score.
        recent = [
            r
            for r in rows
            if (now - r["timestamp"]) <= timedelta(minutes=FOCUS_WINDOW_MIN)
        ]
        if not recent:
            return FocusState.NORMAL

        weighted = self._weighted_focus(recent)
        if weighted >= FOCUSED_THRESHOLD:
            return FocusState.FOCUSED
        return FocusState.NORMAL

    def filter(self, insights: list[Insight]) -> list[Insight]:
        """Return insights appropriate for the current state.

        Focused: only high-confidence insights (score >= FOCUSED_MIN_SCORE).
        Insights with bypass_focus_shield=True always pass through.

        Idle: pass through (tray layer may suppress notifications separately).
        Normal: pass through.
        """
        state = self.current_state()
        if state != FocusState.FOCUSED:
            return insights
        return [
            i for i in insights if i.score >= FOCUSED_MIN_SCORE or i.bypass_focus_shield
        ]

    def should_notify(self) -> bool:
        """Whether tray notifications should fire right now.

        Currently unused — no proactive notification system exists yet.
        Wire this check into the notification dispatch once Phase 3 adds
        features that push insights unprompted (Intention Forecasting,
        Knowledge Decay, etc.).
        """
        return self.current_state() != FocusState.IDLE

    # ---------- internals ----------

    def _recent_typing_rows(self) -> list[dict]:
        cutoff = (datetime.utcnow() - timedelta(minutes=IDLE_WINDOW_MIN * 2)).isoformat(
            sep=" ", timespec="seconds"
        )

        cur = self.memory.conn.cursor()
        cur.execute(
            "SELECT timestamp, metadata FROM observations "
            "WHERE source = 'typing_dynamics' AND timestamp >= ? "
            "ORDER BY timestamp ASC",
            (cutoff,),
        )
        result = []
        for ts, metadata in cur.fetchall():
            try:
                parsed = datetime.fromisoformat(ts)
            except (TypeError, ValueError):
                continue
            score = self._extract_score(metadata)
            if score is None:
                continue
            result.append({"timestamp": parsed, "focus_score": score})
        return result

    @staticmethod
    def _extract_score(metadata: str | None) -> float | None:
        """Pull focus_score from a stored metadata JSON blob."""
        if not metadata:
            return None
        import json

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

    @staticmethod
    def _weighted_focus(rows: list[dict]) -> float:
        """Weight more recent samples higher.

        Weights grow linearly with index so the latest observation has
        the most influence.
        """
        if not rows:
            return 0.0
        total_weight = 0.0
        weighted_sum = 0.0
        for i, row in enumerate(rows):
            weight = i + 1
            weighted_sum += row["focus_score"] * weight
            total_weight += weight
        return weighted_sum / total_weight if total_weight else 0.0
