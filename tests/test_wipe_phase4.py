"""Tests for G3 wipe registry and MemoryStore.wipe() integration.

Covers PRD §22.21.4:
- Every Phase 4 table ends empty after wipe.
- Vision captions (observations with vision_* source) are removed.
- Temp audio dir is deleted.
- Full wipe < 5 s with populated data.
- Non-content config/consent rows survive (existing semantics).
- A failing handler does not prevent other handlers from running.
"""

import time
from pathlib import Path

import pytest

from shadow.memory import wipe_registry
from shadow.memory.wipe_registry import register_phase4_handlers, run_all


@pytest.fixture
def populated(phase4_test_tables, now_epoch):
    conn = phase4_test_tables
    with conn:
        for i in range(50):
            conn.execute(
                "INSERT INTO observations(ts, source, text) VALUES (?, 'vision_auto', 'cap')",
                (now_epoch - i,),
            )
            conn.execute(
                "INSERT INTO observations(ts, source, text) VALUES (?, 'screen_ua', 'uia')",
                (now_epoch - i,),
            )
            conn.execute(
                "INSERT INTO digests(kind, period_start_utc, content_json) VALUES ('daily', ?, '{}')",
                (now_epoch - i,),
            )
            conn.execute(
                "INSERT INTO notification_summaries(window_end, summary_text) VALUES (?, 'n')",
                (now_epoch - i,),
            )
            conn.execute(
                "INSERT INTO ethical_values(text, updated_at) VALUES ('v', ?)",
                (now_epoch,),
            )
            conn.execute(
                "INSERT INTO weaver_insights(status, created_at, statement) VALUES ('new', ?, 's')",
                (now_epoch,),
            )
            conn.execute(
                "INSERT INTO clone_sessions(clone_id, created_at) VALUES (?, ?)",
                (f"c{i}", now_epoch),
            )
    return conn


def _count(conn, table, where="", params=()):
    q = f"SELECT COUNT(*) FROM {table}"
    if where:
        q += f" WHERE {where}"
    return conn.execute(q, params).fetchone()[0]


def test_every_phase4_table_empties(populated, tmp_path):
    conn = populated
    register_phase4_handlers()

    # Simulate the temp audio dir.
    asr_dir = Path(__import__("tempfile").gettempdir()) / "shadow_asr"
    asr_dir.mkdir(exist_ok=True)
    (asr_dir / "tmp.wav").write_bytes(b"x")

    with conn:
        run_all(conn, memory_store=None)

    for table in (
        "ethical_values",
        "clone_sessions",
        "clone_promotions",
        "weaver_insights",
        "digests",
        "notification_summaries",
    ):
        assert _count(conn, table) == 0, f"{table} not empty"

    # Vision captions gone; UIA observations preserved (wipe only removes vision_*).
    assert (
        _count(conn, "observations", "source IN ('vision_auto','vision_continuous')")
        == 0
    )
    assert _count(conn, "observations") > 0  # UIA rows preserved

    # Temp audio dir deleted.
    assert not asr_dir.exists()


def test_failing_handler_does_not_block_others(populated):
    conn = populated

    def boom(_c, _m):
        raise RuntimeError("nope")

    wipe_registry.register("boom", boom)
    wipe_registry.register(
        "digests", lambda c, m: c.execute("DELETE FROM digests").rowcount
    )

    with conn:
        results = run_all(conn, memory_store=None)

    assert results["boom"] == -1
    assert results["digests"] >= 0
    assert _count(conn, "digests") == 0


def test_wipe_under_5s(populated):
    conn = populated
    register_phase4_handlers()
    start = time.perf_counter()
    with conn:
        run_all(conn, memory_store=None)
    elapsed = time.perf_counter() - start
    assert elapsed < 5.0, f"wipe took {elapsed:.2f}s (>5s)"


def test_config_rows_preserved(populated):
    """Wipe should not remove config/consent rows."""
    conn = populated
    with conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS app_config (key TEXT PRIMARY KEY, value TEXT)"
        )
        conn.execute("INSERT INTO app_config(key, value) VALUES ('theme', 'dark')")
        register_phase4_handlers()
        run_all(conn, memory_store=None)
    row = conn.execute("SELECT value FROM app_config WHERE key='theme'").fetchone()
    assert row == ("dark",)


def test_clone_idempotent_wipe(populated):
    """Wipe twice in a row is safe."""
    conn = populated
    register_phase4_handlers()
    with conn:
        run_all(conn, memory_store=None)
    with conn:
        run_all(conn, memory_store=None)
    assert _count(conn, "clone_sessions") == 0


def test_no_orphan_rows_after_cascade(populated):
    """If real schemas are added later with FK cascades, wipe must leave no orphans."""
    conn = populated
    register_phase4_handlers()
    with conn:
        run_all(conn, memory_store=None)
    # No orphans expected because each registered table is deleted directly.
    for table in ("clone_promotions", "weaver_insights"):
        assert _count(conn, table) == 0
