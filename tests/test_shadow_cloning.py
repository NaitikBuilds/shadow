"""Tests for C10: Shadow Cloning session registry + read-only facade."""

from __future__ import annotations

import pytest

from shadow.agent.shadow_cloning import (
    CloneManager,
    CloneMemoryFacade,
)
from shadow.memory import MemoryStore

pytestmark = pytest.mark.p4


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def memory(tmp_path):
    s = MemoryStore(str(tmp_path / "test.db"))
    yield s
    s.close()


@pytest.fixture
def manager(memory):
    return CloneManager(memory, config={"clone_max_concurrent": 2})


def _seed_observations(memory, n=5, source="active_window"):
    ids = []
    for i in range(n):
        cur = memory.conn.execute(
            "INSERT INTO observations(timestamp, source, content) " "VALUES (?, ?, ?)",
            (f"2026-10-{i+1:02d} 12:00:00", source, f"obs {i}"),
        )
        ids.append(cur.lastrowid)
    memory.conn.commit()
    return ids


# ---------------------------------------------------------------------------
# Ephemeral store sanity — proves :memory: MemoryStore works
# ---------------------------------------------------------------------------
def test_ephemeral_memory_store_creation():
    s = MemoryStore(":memory:")
    try:
        # Schema should be fully migrated.
        tables = {
            r[0]
            for r in s.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "observations" in tables
        assert "vec_observations" in tables
    finally:
        s.close()


# ---------------------------------------------------------------------------
# Facade structural guarantees (CLN-01)
# ---------------------------------------------------------------------------
_WRITE_METHODS = (
    "add_observation",
    "add_embedding",
    "upsert_entity",
    "add_edge",
    "link_entity_to_observation",
    "log_activity",
    "set_meta",
    "get_meta",
    "set_consent",
    "seed_consents",
    "ensure_consent",
    "wipe",
    "recent_activity",
)


def test_facade_has_no_write_methods(memory):
    facade = CloneMemoryFacade(memory, {"time_range": {}})
    for m in _WRITE_METHODS:
        assert not hasattr(facade, m), f"facade must not expose {m}"


def test_facade_has_no_raw_connection(memory):
    facade = CloneMemoryFacade(memory, {"time_range": {}})
    assert not hasattr(facade, "conn")
    assert not hasattr(facade, "_conn")
    # Name-mangled backing store is inaccessible via the usual name
    assert not hasattr(facade, "_memory")


def test_facade_read_methods_present(memory):
    facade = CloneMemoryFacade(memory, {"time_range": {}})
    for m in (
        "search_observations",
        "observations_between",
        "search_similar",
        "entities_for_observation",
        "recent_entities",
    ):
        assert callable(getattr(facade, m))


def test_facade_getattr_for_write_raises(memory):
    facade = CloneMemoryFacade(memory, {"time_range": {}})
    with pytest.raises(AttributeError):
        facade.add_observation("x", "test")


# ---------------------------------------------------------------------------
# Facade reads
# ---------------------------------------------------------------------------
def test_facade_search_delegates(memory):
    _seed_observations(memory, n=3)
    facade = CloneMemoryFacade(memory, {"time_range": {}})
    rows = facade.search_observations(limit=10)
    assert len(rows) == 3


def test_facade_filters_blocked_sources(memory):
    _seed_observations(memory, n=3, source="active_window")
    _seed_observations(memory, n=2, source="screen_vision")
    facade = CloneMemoryFacade(
        memory,
        {"time_range": {}},
        blocked_sources={"screen_vision"},
    )
    rows = facade.search_observations(limit=20)
    sources = {r[2] for r in rows}
    assert "screen_vision" not in sources
    assert "active_window" in sources


def test_facade_respects_scope_time_range(memory):
    _seed_observations(memory, n=5)  # dates 2026-10-01 .. 05
    facade = CloneMemoryFacade(
        memory,
        {"time_range": {"start": "2026-10-02 00:00:00", "end": "2026-10-03 23:59:59"}},
    )
    rows = facade.search_observations(limit=20)
    for _, ts, _, _ in rows:
        assert "2026-10-02" in ts or "2026-10-03" in ts


# ---------------------------------------------------------------------------
# Session creation
# ---------------------------------------------------------------------------
def test_create_returns_clone(manager):
    s = manager.create("what-if", {"time_range": {"start": "2026-10-01 00:00:00"}})
    assert s.is_active
    assert s.name == "what-if"
    assert s.status == "active"


def test_create_rejects_empty_name(manager):
    with pytest.raises(ValueError):
        manager.create("", {"time_range": {"start": "2026-10-01 00:00:00"}})


def test_create_rejects_long_name(manager):
    with pytest.raises(ValueError):
        manager.create("x" * 61, {"time_range": {"start": "2026-10-01 00:00:00"}})


def test_create_rejects_empty_scope(manager):
    with pytest.raises(ValueError):
        manager.create("what-if", {})


def test_create_enforces_concurrent_limit(memory):
    mgr = CloneManager(memory, config={"clone_max_concurrent": 2})
    mgr.create("a", {"time_range": {"start": "2026-10-01 00:00:00"}})
    mgr.create("b", {"time_range": {"start": "2026-10-01 00:00:00"}})
    with pytest.raises(RuntimeError, match="clone_max_concurrent"):
        mgr.create("c", {"time_range": {"start": "2026-10-01 00:00:00"}})


def test_create_rejects_duplicate_active_name(manager):
    manager.create("dup", {"time_range": {"start": "2026-10-01 00:00:00"}})
    with pytest.raises(ValueError, match="already exists"):
        manager.create("dup", {"time_range": {"start": "2026-10-01 00:00:00"}})


# ---------------------------------------------------------------------------
# Content + isolation (CLN-01, CLN-03)
# ---------------------------------------------------------------------------
def test_add_message(manager):
    s = manager.create("x", {"time_range": {"start": "2026-10-01 00:00:00"}})
    m = s.add_message("user", "what if I quit?")
    assert m["role"] == "user"
    assert s.list_messages() == [m]


def test_artifact_labeled_simulation(manager):
    s = manager.create("x", {"time_range": {"start": "2026-10-01 00:00:00"}})
    a = s.add_artifact("simulated output")
    assert a["label"] == "simulation"
    assert a["content_hash"]


def test_primary_untouched_by_clone_writes(memory, manager):
    before = memory.conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    s = manager.create("x", {"time_range": {"start": "2026-10-01 00:00:00"}})
    s.add_message("user", "hello")
    s.add_artifact("sim out")
    after = memory.conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    assert before == after


# ---------------------------------------------------------------------------
# Discard (CLN-02)
# ---------------------------------------------------------------------------
def test_discard_closes_ephemeral(manager):
    s = manager.create("x", {"time_range": {"start": "2026-10-01 00:00:00"}})
    assert s.ephemeral is not None
    s.discard()
    assert s.ephemeral is None
    assert s.status == "discarded"


def test_discard_clears_content(manager):
    s = manager.create("x", {"time_range": {"start": "2026-10-01 00:00:00"}})
    s.add_message("user", "hi")
    s.add_artifact("out")
    s.discard()
    assert s.list_messages() == []
    assert s.list_artifacts() == []


def test_discard_idempotent(manager):
    s = manager.create("x", {"time_range": {"start": "2026-10-01 00:00:00"}})
    assert s.discard() is True
    assert s.discard() is False


def test_manager_discard_by_id(memory, manager):
    s = manager.create("x", {"time_range": {"start": "2026-10-01 00:00:00"}})
    assert manager.discard(s.clone_id) is True
    assert manager.get(s.clone_id) is None


# ---------------------------------------------------------------------------
# Startup sweep (CLN-06)
# ---------------------------------------------------------------------------
def test_startup_sweep_marks_active_rows_expired(memory):
    mgr = CloneManager(memory, config={})
    mgr.create("orphan", {"time_range": {"start": "2026-10-01 00:00:00"}})

    # Simulate crash: create a fresh manager against the same DB
    mgr2 = CloneManager(memory, config={})
    swept = mgr2.startup_sweep()
    assert swept >= 1
    rows = memory.conn.execute("SELECT status FROM clone_sessions").fetchall()
    assert all(r[0] == "expired" for r in rows)


# ---------------------------------------------------------------------------
# Promote stub (C12)
# ---------------------------------------------------------------------------
def test_promote_raises_not_implemented(manager):
    s = manager.create("x", {"time_range": {"start": "2026-10-01 00:00:00"}})
    a = s.add_artifact("out")
    with pytest.raises(NotImplementedError):
        s.promote(a["artifact_id"])
