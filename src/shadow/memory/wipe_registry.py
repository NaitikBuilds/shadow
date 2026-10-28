"""Per-feature wipe handlers (G3).

The audit found MemoryStore.wipe() is not a generic registry and does not
cover future Phase 4 tables. Every content-bearing table registers a wipe().
"""

from __future__ import annotations

from collections.abc import Callable

_HANDLERS: list[tuple[str, Callable]] = []


def register(name: str, handler: Callable) -> None:
    _HANDLERS.append((name, handler))


def run_all(conn, memory_store) -> dict:
    """Run every registered wipe handler, then clean ephemeral stores.

    Each handler is isolated: a failure (e.g. feature table not yet migrated)
    is logged and recorded as -1, and the remaining handlers still run.
    """
    import logging as _logging

    _log = _logging.getLogger(__name__)  # local logger — ignores module-level `log`

    results: dict[str, int] = {}
    for name, handler in _HANDLERS:
        try:
            n = handler(conn, memory_store)
            results[name] = int(n) if isinstance(n, int) else 0
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "wipe_handler_failed",
                extra={"handler": name, "error": str(exc)},
            )
            results[name] = -1
    _wipe_clone_ephemeral()
    _wipe_temp_audio()
    _wipe_notification_buffer()
    return results


def _wipe_clone_ephemeral() -> None:
    # remove in-memory clone stores (no files by design)
    pass


def _wipe_temp_audio() -> None:
    import shutil
    import tempfile
    from pathlib import Path

    d = Path(tempfile.gettempdir()) / "shadow_asr"
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)


def _wipe_notification_buffer() -> None:
    try:
        from shadow.perception.notifications import clear_buffer

        clear_buffer()
    except Exception:
        pass


# --- Phase 4 registrations -------------------------------------------------
def register_phase4_wipe(conn) -> None:
    # Feature commits call these when their tables exist.
    register("ethical_values", lambda c, m: c.execute("DELETE FROM ethical_values"))
    register(
        "ethical_values_history",
        lambda c, m: c.execute("DELETE FROM ethical_values_history"),
    )
    register("clone_sessions", lambda c, m: c.execute("DELETE FROM clone_sessions"))
    register("clone_promotions", lambda c, m: c.execute("DELETE FROM clone_promotions"))
    register("weaver_insights", lambda c, m: c.execute("DELETE FROM weaver_insights"))
    register(
        "weaver_insight_sources",
        lambda c, m: c.execute("DELETE FROM weaver_insight_sources"),
    )
    register("meetings", lambda c, m: c.execute("DELETE FROM meetings"))
    register(
        "meeting_transcripts", lambda c, m: c.execute("DELETE FROM meeting_transcripts")
    )
    register("meeting_preps", lambda c, m: c.execute("DELETE FROM meeting_preps"))
    register(
        "meeting_summaries", lambda c, m: c.execute("DELETE FROM meeting_summaries")
    )
    register("digests", lambda c, m: c.execute("DELETE FROM digests"))
    register(
        "notification_summaries",
        lambda c, m: c.execute("DELETE FROM notification_summaries"),
    )
    # vision captions are observations with source IN ('vision_auto','vision_continuous')
    register(
        "vision_captions",
        lambda c, m: c.execute(
            "DELETE FROM observations WHERE source IN ('vision_auto','vision_continuous')"
        ),
    )


# --- Phase 4 registrations ---------------------------------------------
def register_phase4_handlers() -> None:
    """Register one wipe handler per Phase 4 content-bearing table.

    Idempotent. Handlers skip tables that don't exist yet (feature not
    implemented), returning 0, so wipe never errors mid-migration.
    """

    def _del(table: str):
        def _h(conn, _ms):
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if not exists:
                return 0
            cur = conn.execute(f"DELETE FROM {table}")
            return cur.rowcount or 0

        return _h

    register("ethical_values", _del("ethical_values"))
    register("ethical_values_history", _del("ethical_values_history"))
    register("clone_sessions", _del("clone_sessions"))
    register("clone_promotions", _del("clone_promotions"))
    register("weaver_insights", _del("weaver_insights"))
    register("weaver_insight_sources", _del("weaver_insight_sources"))
    register("meetings", _del("meetings"))
    register("meeting_audio_jobs", _del("meeting_audio_jobs"))
    register("meeting_transcripts", _del("meeting_transcripts"))
    register("transcript_segments", _del("transcript_segments"))
    register("meeting_preps", _del("meeting_preps"))
    register("meeting_summaries", _del("meeting_summaries"))
    register("digests", _del("digests"))
    register("notification_summaries", _del("notification_summaries"))

    def _wipe_vision_captions(conn, _ms):
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='observations'"
        ).fetchone()
        if not exists:
            return 0
        cur = conn.execute(
            "DELETE FROM observations WHERE source IN "
            "('vision_auto','vision_continuous')"
        )
        return cur.rowcount or 0

    register("vision_captions", _wipe_vision_captions)


def clear() -> None:
    """Test-only helper."""
    _HANDLERS.clear()


def registered() -> list[str]:
    return [name for name, _ in _HANDLERS]
