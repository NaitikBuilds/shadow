import sqlite3
import time

import pytest

from tests._phase4_spies import (
    CloudBackendSpy,
    FakeClock,
    FakeConsent,
    FakeVLM,
    NetworkBlocker,
    Phase4Spies,
    VisionRouterSpy,
)


@pytest.fixture
def tmp_db_path(tmp_path):
    return tmp_path / "shadow_test.db"


@pytest.fixture
def db_conn(tmp_db_path):
    """File-backed SQLite with FK on and WAL enabled (WAL needs a file)."""
    conn = sqlite3.connect(tmp_db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    yield conn
    conn.close()


@pytest.fixture
def phase4_test_tables(db_conn):
    """Create a minimal set of tables used by retention and wipe tests.

    These mimic the tables Phase 4 features will add; the tests verify the
    registry mechanism, not the feature schemas themselves.
    """
    with db_conn:
        db_conn.executescript("""
            CREATE TABLE schema_meta (current_version INTEGER NOT NULL);
            INSERT INTO schema_meta(current_version) VALUES (7);

            CREATE TABLE observations (
                id INTEGER PRIMARY KEY,
                ts INTEGER NOT NULL,
                source TEXT NOT NULL,
                text TEXT
            );

            CREATE TABLE digests (
                digest_id INTEGER PRIMARY KEY,
                kind TEXT NOT NULL,
                period_start_utc INTEGER NOT NULL,
                content_json TEXT
            );

            CREATE TABLE notification_summaries (
                summary_id INTEGER PRIMARY KEY,
                window_end INTEGER NOT NULL,
                summary_text TEXT
            );

            CREATE TABLE ethical_values (
                value_id INTEGER PRIMARY KEY,
                text TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            );

            CREATE TABLE weaver_insights (
                insight_id INTEGER PRIMARY KEY,
                status TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                statement TEXT
            );

            CREATE TABLE clone_sessions (
                clone_id TEXT PRIMARY KEY,
                created_at INTEGER NOT NULL
            );

            CREATE TABLE clone_promotions (
                promotion_id INTEGER PRIMARY KEY,
                clone_id TEXT,
                promoted_at INTEGER
            );
        """)
    return db_conn


@pytest.fixture(autouse=True)
def reset_registries():
    """Defensive: Phase 4 registries may be added incrementally during
    Stage A. Only clear() if the function exists, so existing tests
    (test_retention.py, test_migrations.py, test_consents.py) keep passing
    while new modules are wired up.
    """
    mods = []
    try:
        from shadow.memory import retention_registry, wipe_registry

        mods = [retention_registry, wipe_registry]
    except ImportError:
        pass

    for m in mods:
        if hasattr(m, "clear"):
            m.clear()

    yield

    for m in mods:
        if hasattr(m, "clear"):
            m.clear()


@pytest.fixture
def now_epoch():
    return int(time.time())


# ---------------------------------------------------------------------------
# Phase 4 test harness (C02)
# ---------------------------------------------------------------------------


@pytest.fixture
def phase4_spies(monkeypatch):
    """Bundle of Phase 4 spies. Presets consent to nothing granted.

    Tests can opt into network blocking via:

        with phase4_spies.network_blocker:
            ... code under test ...
    """
    bundle = Phase4Spies(
        fake_vlm=FakeVLM(),
        cloud_spy=CloudBackendSpy(),
        vision_router_spy=VisionRouterSpy(),
        network_blocker=NetworkBlocker(),
        clock=FakeClock(),
        consent=FakeConsent(),
    )
    return bundle
