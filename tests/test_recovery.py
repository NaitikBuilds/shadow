from datetime import datetime, timedelta

import pytest

from shadow.memory import CrashRecovery, MemoryStore


class FakeBackend:
    """Embed returns a fixed 384-dim vector."""

    def __init__(self, fail: bool = False):
        self.fail = fail

    def embed(self, text: str) -> list[float]:
        if self.fail:
            raise RuntimeError("embed failed")
        return [0.0] * 384


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "recovery.db"))
    yield s
    s.close()


def _iso(hours_ago: float = 0) -> str:
    dt = datetime.utcnow() - timedelta(hours=hours_ago)
    return dt.isoformat(sep=" ", timespec="seconds")


def _log(store, action: str, when: str):
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO activity_log (timestamp, action, details) VALUES (?, ?, '')",
        (when, action),
    )
    store.conn.commit()


def _orphan(store, content: str, when: str) -> int:
    """Observation with no embedding."""
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO observations (timestamp, source, content) VALUES (?, 'test', ?)",
        (when, content),
    )
    store.conn.commit()
    return cur.lastrowid


def test_first_run_detection(store):
    rec = CrashRecovery(store, FakeBackend(), {})
    assert rec._detect_shutdown() == "first_run"


def test_clean_shutdown_detection(store):
    _log(store, "app_start", _iso(hours_ago=2))
    _log(store, "app_stop", _iso(hours_ago=1))
    rec = CrashRecovery(store, FakeBackend(), {})
    assert rec._detect_shutdown() == "clean"


def test_unexpected_shutdown_detection(store):
    _log(store, "app_start", _iso(hours_ago=2))
    # no app_stop
    rec = CrashRecovery(store, FakeBackend(), {})
    assert rec._detect_shutdown() == "unexpected"


def test_orphan_reembedded(store):
    obs_id = _orphan(store, "a" * 100, _iso(hours_ago=30))
    rec = CrashRecovery(store, FakeBackend(), {})
    reembedded, dropped = rec._recover_orphans()
    assert reembedded == 1
    assert dropped == 0

    cur = store.conn.cursor()
    cur.execute("SELECT COUNT(*) FROM vec_observations WHERE rowid = ?", (obs_id,))
    assert cur.fetchone()[0] == 1


def test_orphan_dropped_when_too_old(store):
    obs_id = _orphan(store, "a" * 100, _iso(hours_ago=100))
    rec = CrashRecovery(store, FakeBackend(), {})
    reembedded, dropped = rec._recover_orphans()
    assert reembedded == 0
    assert dropped == 1

    cur = store.conn.cursor()
    cur.execute("SELECT COUNT(*) FROM observations WHERE id = ?", (obs_id,))
    assert cur.fetchone()[0] == 0


def test_orphan_dropped_when_reembed_fails(store):
    _orphan(store, "a" * 100, _iso(hours_ago=30))
    rec = CrashRecovery(store, FakeBackend(fail=True), {})
    reembedded, dropped = rec._recover_orphans()
    assert reembedded == 0
    assert dropped == 1


def test_empty_orphan_dropped(store):
    _orphan(store, "   ", _iso(hours_ago=30))
    rec = CrashRecovery(store, FakeBackend(), {})
    reembedded, dropped = rec._recover_orphans()
    assert reembedded == 0
    assert dropped == 1


def test_startup_summary_shape(store):
    rec = CrashRecovery(store, FakeBackend(), {})
    summary = rec.run_startup_recovery()
    assert "shutdown_status" in summary
    assert "orphans_reembedded" in summary
    assert "orphans_dropped" in summary


def test_unexpected_shutdown_logs_activity(store):
    _log(store, "app_start", _iso(hours_ago=2))
    rec = CrashRecovery(store, FakeBackend(), {})
    rec.run_startup_recovery()

    cur = store.conn.cursor()
    cur.execute("SELECT COUNT(*) FROM activity_log WHERE action = 'crash_recovered'")
    assert cur.fetchone()[0] == 1
