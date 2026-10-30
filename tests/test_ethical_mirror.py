"""Tests for C07: Ethical Mirror values store.

Covers PRD §22.4.2 / §22.6.1 acceptance criteria:
  - AC-P4-ETH-03 — CRUD, persistence
  - AC-P4-ETH-04 — validation, empty/overlong rejected
  - AC-P4-ETH-07 — source=user_stated enforced, no inferred allowed
  - AC-P4-ETH-11 — delete-all and wipe removes values and history
  - AC-P4-ETH-12 — opt-out hides feature, values kept
"""

from __future__ import annotations

import sqlite3

import pytest

from shadow.agent.ethical_mirror import (
    COMPLETE_PROFILE_MIN,
    EthicalValueDuplicateError,
    EthicalValueNotFoundError,
    EthicalValuesStore,
    EthicalValueValidationError,
)
from shadow.memory import MemoryStore
from shadow.memory.wipe_registry import register_phase4_handlers, run_all

pytestmark = pytest.mark.p4


@pytest.fixture
def memory(tmp_path):
    s = MemoryStore(str(tmp_path / "test.db"))
    yield s
    s.close()


@pytest.fixture
def store(memory):
    return EthicalValuesStore(memory)


# ---------------------------------------------------------------------------
# Schema / migration
# ---------------------------------------------------------------------------
def test_migration_creates_tables(memory):
    tables = {
        r[0]
        for r in memory.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "ethical_values" in tables
    assert "ethical_values_history" in tables


def test_schema_enforces_source_user_stated(memory):
    """AC-P4-ETH-07: cannot insert a non-user_stated source."""
    with pytest.raises(sqlite3.IntegrityError):
        memory.conn.execute(
            "INSERT INTO ethical_values"
            "(text, position, status, source, version, created_at, updated_at) "
            "VALUES ('x', 0, 'active', 'inferred', 1, 0, 0)"
        )


def test_schema_rejects_overlong_text_at_db_level(memory):
    """Second line of defense: DB CHECK also rejects >300 chars."""
    with pytest.raises(sqlite3.IntegrityError):
        memory.conn.execute(
            "INSERT INTO ethical_values"
            "(text, position, status, source, version, created_at, updated_at) "
            "VALUES (?, 0, 'active', 'user_stated', 1, 0, 0)",
            ("x" * 301,),
        )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------
def test_add_creates_active_value(store):
    vid = store.add("Honesty in feedback")
    row = store.get(vid)
    assert row is not None
    assert row["text"] == "Honesty in feedback"
    assert row["status"] == "active"
    assert row["source"] == "user_stated"
    assert row["version"] == 1


def test_add_appends_position(store):
    a = store.add("A")
    b = store.add("B")
    c = store.add("C")
    assert (
        store.get(a)["position"] < store.get(b)["position"] < store.get(c)["position"]
    )


def test_add_rejects_empty(store):
    with pytest.raises(EthicalValueValidationError):
        store.add("   ")


def test_add_rejects_overlong(store):
    with pytest.raises(EthicalValueValidationError):
        store.add("x" * 301)


def test_add_rejects_non_string(store):
    with pytest.raises(EthicalValueValidationError):
        store.add(123)  # type: ignore[arg-type]


def test_add_rejects_duplicate_active(store):
    store.add("Kindness matters")
    with pytest.raises(EthicalValueDuplicateError):
        store.add("kindness MATTERS")  # normalized duplicate


def test_add_after_archive_same_text_ok(store):
    vid = store.add("Reversibility")
    store.archive(vid)
    # Same text after archive is allowed.
    new_vid = store.add("Reversibility")
    assert new_vid != vid


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------
def test_update_text_records_history(store):
    vid = store.add("original")
    assert store.update(vid, text="updated")
    row = store.get(vid)
    assert row["text"] == "updated"
    assert row["version"] == 2
    hist = store._conn.execute(
        "SELECT old_text, change_type FROM ethical_values_history "
        "WHERE value_id = ?",
        (vid,),
    ).fetchall()
    assert ("original", "update") in hist


def test_update_noop_returns_false(store):
    vid = store.add("x")
    assert store.update(vid) is False  # no args
    assert store.update(vid, text="x") is False  # same text


def test_update_rejects_duplicate(store):
    a = store.add("A")
    store.add("B")
    with pytest.raises(EthicalValueDuplicateError):
        store.update(a, text="B")


def test_update_unknown_id_raises(store):
    with pytest.raises(EthicalValueNotFoundError):
        store.update(99999, text="x")


# ---------------------------------------------------------------------------
# Delete / archive / restore
# ---------------------------------------------------------------------------
def test_delete_removes_row_and_history(store, memory):
    vid = store.add("a")
    store.update(vid, text="b")  # creates history
    assert store.delete(vid) is True
    assert store.get(vid) is None
    hist = memory.conn.execute(
        "SELECT COUNT(*) FROM ethical_values_history WHERE value_id = ?", (vid,)
    ).fetchone()
    assert hist[0] == 0


def test_delete_unknown_returns_false(store):
    assert store.delete(99999) is False


def test_archive_removes_from_active(store):
    vid = store.add("x")
    assert store.archive(vid) is True
    assert store.get(vid)["status"] == "archived"
    assert vid not in [v["value_id"] for v in store.list_active()]
    assert vid in [v["value_id"] for v in store.list_archived()]


def test_archive_idempotent(store):
    vid = store.add("x")
    assert store.archive(vid) is True
    assert store.archive(vid) is False


def test_restore_returns_to_active(store):
    vid = store.add("x")
    store.archive(vid)
    assert store.restore(vid) is True
    assert store.get(vid)["status"] == "active"


# ---------------------------------------------------------------------------
# Reorder
# ---------------------------------------------------------------------------
def test_reorder_changes_positions(store):
    a = store.add("a")
    b = store.add("b")
    c = store.add("c")
    store.reorder([c, a, b])
    order = [v["value_id"] for v in store.list_active()]
    assert order == [c, a, b]


# ---------------------------------------------------------------------------
# Limited mode
# ---------------------------------------------------------------------------
def test_limited_mode_when_under_ten(store):
    for i in range(9):
        store.add(f"value {i}")
    assert store.count_active() == 9
    assert store.is_limited_mode() is True


def test_full_mode_at_ten(store):
    for i in range(COMPLETE_PROFILE_MIN):
        store.add(f"value {i}")
    assert store.count_active() == COMPLETE_PROFILE_MIN
    assert store.is_limited_mode() is False


# ---------------------------------------------------------------------------
# Delete-all + wipe integration
# ---------------------------------------------------------------------------
def test_clear_all_removes_everything(store, memory):
    for i in range(3):
        store.add(f"v{i}")
    assert store.clear_all() == 3
    assert store.count_active() == 0
    remaining = memory.conn.execute("SELECT COUNT(*) FROM ethical_values").fetchone()[0]
    assert remaining == 0


def test_wipe_clears_values(store, memory):
    """Full wipe must remove ethical_values and history."""
    store.add("a")
    store.add("b")
    register_phase4_handlers()
    with memory.conn:
        run_all(memory.conn, memory)
    assert memory.conn.execute("SELECT COUNT(*) FROM ethical_values").fetchone()[0] == 0
    assert (
        memory.conn.execute("SELECT COUNT(*) FROM ethical_values_history").fetchone()[0]
        == 0
    )


# ---------------------------------------------------------------------------
# Retention: ethical values never pruned
# ---------------------------------------------------------------------------
def test_retention_never_prunes_ethical_values(store, memory):
    """register_phase4_defaults registers days=None — prune_all skips them."""
    from shadow.memory.retention import prune_all
    from shadow.memory.retention_registry import (
        all_policies,
        register_phase4_defaults,
    )

    # Register policies if not already (bootstrap does this in real app).
    if not any(p.table == "ethical_values" for p in all_policies()):
        register_phase4_defaults()

    vid = store.add("ancient value")
    # Backdate by 10 years at the DB level.
    old_ms = 0  # epoch
    memory.conn.execute(
        "UPDATE ethical_values SET updated_at = ? WHERE value_id = ?",
        (old_ms, vid),
    )
    memory.conn.commit()
    prune_all(memory.conn)
    assert store.get(vid) is not None  # never pruned
