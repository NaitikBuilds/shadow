import sqlite3

import pytest

from shadow.memory import MemoryStore
from shadow.memory.migrations import MigrationRunner


@pytest.fixture
def temp_db(tmp_path):
    return str(tmp_path / "test.db")


def test_fresh_db_migrates_to_latest(temp_db):
    store = MemoryStore(temp_db)
    try:
        cur = store.conn.cursor()
        cur.execute("SELECT value FROM schema_meta WHERE key = 'current_version'")
        version = int(cur.fetchone()[0])
        assert version >= 1  # at least the baseline
        # Verify the ambient state table from migration 002 exists
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='ambient_task_state'"
        )
        assert cur.fetchone() is not None
    finally:
        store.close()


def test_all_phase2_tables_exist(temp_db):
    store = MemoryStore(temp_db)
    try:
        cur = store.conn.cursor()
        for table in (
            "observations",
            "intentions",
            "activity_log",
            "consents",
            "consent_audit",
            "entities",
            "edges",
            "observation_entities",
        ):
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            )
            assert cur.fetchone() is not None, f"missing table: {table}"
    finally:
        store.close()


def test_reopen_is_noop(temp_db):
    """Opening the same DB twice should not re-run migrations."""
    s1 = MemoryStore(temp_db)
    s1.close()

    s2 = MemoryStore(temp_db)
    try:
        cur = s2.conn.cursor()
        cur.execute("SELECT value FROM schema_meta WHERE key = 'current_version'")
        assert int(cur.fetchone()[0]) >= 1
    finally:
        s2.close()


def test_retrofit_existing_db(temp_db):
    """A DB created by the old _init_schema (no schema_meta) upgrades cleanly."""
    conn = sqlite3.connect(temp_db)
    conn.enable_load_extension(True)
    import sqlite_vec

    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.executescript("""
        CREATE TABLE observations (id INTEGER PRIMARY KEY, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, source TEXT, content TEXT, metadata TEXT);
        CREATE VIRTUAL TABLE vec_observations USING vec0(embedding float[384]);
    """)
    # Insert a row to prove data is preserved
    conn.execute(
        "INSERT INTO observations (source, content) VALUES ('test', 'legacy row')"
    )
    conn.commit()
    conn.close()

    # Now open through MemoryStore — should add schema_meta and bump to v1
    store = MemoryStore(temp_db)
    try:
        cur = store.conn.cursor()
        cur.execute("SELECT value FROM schema_meta WHERE key = 'current_version'")
        assert int(cur.fetchone()[0]) >= 1

        cur.execute("SELECT COUNT(*) FROM observations")
        assert cur.fetchone()[0] == 1
    finally:
        store.close()


def test_backup_created_before_migration(tmp_path):
    """When there are pending migrations, a backup should exist afterward."""
    db_path = str(tmp_path / "test.db")

    # Seed with old state
    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    import sqlite_vec

    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.executescript("""
        CREATE TABLE observations (id INTEGER PRIMARY KEY, content TEXT);
    """)
    conn.commit()
    conn.close()

    store = MemoryStore(db_path)
    store.close()

    backup_dir = tmp_path / "backups"
    backups = list(backup_dir.glob("shadow_v*.db"))
    assert len(backups) >= 1, "expected at least one backup to be created"


def test_backup_retention(tmp_path, monkeypatch):
    """Only the last 3 backups are retained."""
    db_path = str(tmp_path / "test.db")
    store = MemoryStore(db_path)
    try:
        runner = MigrationRunner(store.conn, db_path)

        # Force 5 backups manually
        for _ in range(5):
            runner._backup(0)

        backups = sorted((tmp_path / "backups").glob("shadow_v*.db"))
        assert len(backups) <= 3
    finally:
        store.close()


def test_missing_migration_dir_is_safe(tmp_path):
    """If no migrations exist, run() returns 0 without error."""
    conn = sqlite3.connect(str(tmp_path / "x.db"))
    runner = MigrationRunner(conn, str(tmp_path / "x.db"))
    # Temporarily monkey the discovery to return nothing
    import shadow.memory.migrations.runner as r

    original = r.MIGRATIONS_DIR
    r.MIGRATIONS_DIR = tmp_path / "nonexistent"
    try:
        version = runner.run()
        assert version == 0
    finally:
        r.MIGRATIONS_DIR = original
        conn.close()


def test_ambient_task_state_table_exists(temp_db):
    """Migration 002 creates the ambient_task_state table."""
    store = MemoryStore(temp_db)
    try:
        cur = store.conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='ambient_task_state'"
        )
        assert cur.fetchone() is not None

        # Verify columns
        cur.execute("PRAGMA table_info(ambient_task_state)")
        cols = {row[1] for row in cur.fetchall()}
        assert {"entity_id", "status", "updated_at"}.issubset(cols)
    finally:
        store.close()
