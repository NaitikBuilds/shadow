"""Tests for G3 retention registry and prune loop.

Covers:
- Boundary pruning for a numeric policy.
- Policies with days=None are skipped.
- Predicate filtering (e.g. stale-only weaver insights).
- Single-transaction semantics: an injected failure rolls back all prunes.
- Idempotency: running twice is safe.
- Clone tables are not pruned (they are wiped, not pruned).
"""

import sqlite3

import pytest

from shadow.memory import retention_registry
from shadow.memory.retention import prune_all

DAY = 86400


def _seed_digest(conn, kind, days_ago, now):
    conn.execute(
        "INSERT INTO digests(kind, period_start_utc, content_json) VALUES (?, ?, ?)",
        (kind, now - days_ago * DAY, "{}"),
    )


def _seed_notification(conn, days_ago, now):
    conn.execute(
        "INSERT INTO notification_summaries(window_end, summary_text) VALUES (?, ?)",
        (now - days_ago * DAY, "n"),
    )


def _seed_weaver(conn, status, days_ago, now):
    conn.execute(
        "INSERT INTO weaver_insights(status, created_at, statement) VALUES (?, ?, ?)",
        (status, now - days_ago * DAY, "s"),
    )


def _count(conn, table, where="", params=()):
    q = f"SELECT COUNT(*) FROM {table}"
    if where:
        q += f" WHERE {where}"
    return conn.execute(q, params).fetchone()[0]


def test_prune_boundary_exact(tmp_path, phase4_test_tables, now_epoch):
    conn = phase4_test_tables
    retention_registry.register(
        retention_registry.RetentionPolicy(
            "digests", 90, "period_start_utc", "kind='daily'"
        )
    )
    # Just inside, exactly at, just outside.
    _seed_digest(conn, "daily", 89, now_epoch)
    _seed_digest(conn, "daily", 90, now_epoch)  # exactly 90 days: < cutoff => deleted
    _seed_digest(conn, "daily", 91, now_epoch)
    conn.commit()

    deleted = prune_all(conn, now_epoch=now_epoch)
    assert deleted["digests"] == 2
    assert _count(conn, "digests", "kind='daily'") == 1


def test_days_none_is_skipped(phase4_test_tables, now_epoch):
    conn = phase4_test_tables
    retention_registry.register(
        retention_registry.RetentionPolicy("ethical_values", None, "updated_at")
    )
    conn.execute(
        "INSERT INTO ethical_values(text, updated_at) VALUES ('v', ?)",
        (now_epoch - 3650 * DAY,),
    )
    conn.commit()
    deleted = prune_all(conn, now_epoch=now_epoch)
    assert "ethical_values" not in deleted or deleted.get("ethical_values", 0) == 0
    assert _count(conn, "ethical_values") == 1


def test_predicate_filters(phase4_test_tables, now_epoch):
    conn = phase4_test_tables
    retention_registry.register(
        retention_registry.RetentionPolicy(
            "weaver_insights", 90, "created_at", "status='stale'"
        )
    )
    _seed_weaver(conn, "stale", 100, now_epoch)
    _seed_weaver(conn, "saved", 100, now_epoch)
    _seed_weaver(conn, "new", 100, now_epoch)
    conn.commit()
    deleted = prune_all(conn, now_epoch=now_epoch)
    assert deleted["weaver_insights"] == 1
    remaining = {
        r[0] for r in conn.execute("SELECT status FROM weaver_insights").fetchall()
    }
    assert remaining == {"saved", "new"}


def test_prune_is_transactional(phase4_test_tables, now_epoch, monkeypatch):
    """If a later prune fails, earlier deletes roll back."""
    conn = phase4_test_tables
    retention_registry.register(
        retention_registry.RetentionPolicy(
            "digests", 90, "period_start_utc", "kind='daily'"
        )
    )
    # Second policy uses a column that doesn't exist on digests -> raises.
    retention_registry.register(
        retention_registry.RetentionPolicy("digests", 1, "no_such_column")
    )
    _seed_digest(conn, "daily", 100, now_epoch)
    conn.commit()

    with pytest.raises(sqlite3.Error):
        prune_all(conn, now_epoch=now_epoch)

    # Rolled back: digest still present.
    assert _count(conn, "digests") == 1


def test_prune_idempotent(phase4_test_tables, now_epoch):
    conn = phase4_test_tables
    retention_registry.register(
        retention_registry.RetentionPolicy(
            "digests", 90, "period_start_utc", "kind='daily'"
        )
    )
    _seed_digest(conn, "daily", 100, now_epoch)
    conn.commit()
    first = prune_all(conn, now_epoch=now_epoch)
    second = prune_all(conn, now_epoch=now_epoch)
    assert first["digests"] == 1
    assert second.get("digests", 0) == 0


def test_clone_tables_not_pruned_by_retention(phase4_test_tables, now_epoch):
    """Clone tables are wiped, not retention-pruned. Ensure no policy touches them."""
    conn = phase4_test_tables
    conn.execute(
        "INSERT INTO clone_sessions(clone_id, created_at) VALUES ('c1', ?)",
        (now_epoch - 999 * DAY,),
    )
    conn.commit()
    # No clone policy is registered by register_phase4_defaults().
    retention_registry.register_phase4_defaults()
    assert all(
        p.table not in ("clone_sessions", "clone_promotions")
        for p in retention_registry.all_policies()
    )
    deleted = prune_all(conn, now_epoch=now_epoch)
    assert deleted.get("clone_sessions", 0) == 0
    assert _count(conn, "clone_sessions") == 1
