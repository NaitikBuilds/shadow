"""Per-table retention registry (G3).

The audit found RetentionPolicy only prunes observations/activity/logs.
Every Phase 4 content-bearing table registers its own policy here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RetentionPolicy:
    table: str
    days: int | None  # None = until user deletes
    column: str  # timestamp column
    predicate: str = ""  # optional SQL predicate, e.g. "kind='daily'"


_REGISTRY: list[RetentionPolicy] = []


def register(policy: RetentionPolicy) -> None:
    _REGISTRY.append(policy)


def all_policies() -> list[RetentionPolicy]:
    return list(_REGISTRY)


# --- Phase 4 registrations (called from each feature's init) --------------
def register_phase4_defaults() -> None:
    register(RetentionPolicy("digests", 90, "period_start_utc", "kind='daily'"))
    register(RetentionPolicy("digests", 364, "period_start_utc", "kind='weekly'"))
    register(RetentionPolicy("meeting_transcripts", 30, "created_at"))
    register(
        RetentionPolicy("transcript_segments", 30, "start_ms")
    )  # cascades with transcript
    register(RetentionPolicy("meeting_preps", 90, "generated_at"))
    register(RetentionPolicy("meeting_summaries", 90, "generated_at"))
    register(RetentionPolicy("notification_summaries", 7, "window_end"))
    register(RetentionPolicy("weaver_insights", 90, "created_at", "status='stale'"))
    register(RetentionPolicy("ethical_values", None, "updated_at"))
    # clone_sessions/clone_promotions: metadata until wipe; not retention-pruned.


def clear() -> None:
    """Test-only helper. Removes all registered policies."""
    _REGISTRY.clear()
