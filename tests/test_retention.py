from datetime import datetime, timedelta

import pytest

from shadow.memory import MemoryStore, RetentionPolicy


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "retention.db"))
    yield s
    s.close()


def _iso(days_ago: float = 0, hours_ago: float = 0) -> str:
    dt = datetime.utcnow() - timedelta(days=days_ago, hours=hours_ago)
    return dt.isoformat(sep=" ", timespec="seconds")


def _add_observation(store, content: str, timestamp: str) -> int:
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO observations (timestamp, source, content) VALUES (?, ?, ?)",
        (timestamp, "active_window", content),
    )
    store.conn.commit()
    return cur.lastrowid


def test_prune_low_value_removes_short_observations(store, tmp_path):
    cfg = {"retention": {"low_value_days": 7}}
    policy = RetentionPolicy(store, cfg, log_dir=tmp_path / "logs")

    _add_observation(store, "hi", _iso(days_ago=10))  # too short
    _add_observation(store, "a" * 100, _iso(days_ago=10))  # long enough
    _add_observation(store, "unknown: ", _iso(days_ago=10))  # unknown proc

    deleted = policy._prune_low_value()
    assert deleted == 2

    cur = store.conn.cursor()
    cur.execute("SELECT COUNT(*) FROM observations")
    assert cur.fetchone()[0] == 1


def test_prune_low_value_respects_age(store, tmp_path):
    cfg = {"retention": {"low_value_days": 7}}
    policy = RetentionPolicy(store, cfg, log_dir=tmp_path / "logs")

    _add_observation(store, "hi", _iso(hours_ago=1))  # recent, should stay
    deleted = policy._prune_low_value()
    assert deleted == 0


def test_prune_by_age_disabled_by_default(store, tmp_path):
    cfg = {"retention": {"observations_days": 0}}
    policy = RetentionPolicy(store, cfg, log_dir=tmp_path / "logs")

    _add_observation(store, "a" * 100, _iso(days_ago=400))
    deleted = policy._prune_by_age()
    assert deleted == 0


def test_prune_by_age_removes_old_observations(store, tmp_path):
    cfg = {"retention": {"observations_days": 30}}
    policy = RetentionPolicy(store, cfg, log_dir=tmp_path / "logs")

    _add_observation(store, "a" * 100, _iso(days_ago=60))
    _add_observation(store, "b" * 100, _iso(days_ago=5))

    deleted = policy._prune_by_age()
    assert deleted == 1


def test_prune_activity_keeps_recent(store, tmp_path):
    cfg = {"retention": {"activity_days": 30}}
    policy = RetentionPolicy(store, cfg, log_dir=tmp_path / "logs")

    # Add an old entry and a recent one
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO activity_log (timestamp, action, details) VALUES (?, ?, ?)",
        (_iso(days_ago=60), "old", ""),
    )
    cur.execute(
        "INSERT INTO activity_log (timestamp, action, details) VALUES (?, ?, ?)",
        (_iso(days_ago=1), "recent", ""),
    )
    store.conn.commit()

    deleted = policy._prune_activity_log()
    # Kept because of the "always keep last 1000" rule
    assert deleted == 0


def test_rotate_error_logs_deletes_old_files(store, tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    old_log = log_dir / "errors_20200101.log"
    old_log.write_text("old", encoding="utf-8")
    recent_log = log_dir / "errors_20991231.log"
    recent_log.write_text("new", encoding="utf-8")

    cfg = {"retention": {"error_logs_days": 30}}
    policy = RetentionPolicy(store, cfg, log_dir=log_dir)
    deleted = policy._rotate_error_logs()

    assert deleted == 1
    assert not old_log.exists()
    assert recent_log.exists()


def test_maybe_run_skips_within_interval(store, tmp_path):
    cfg = {"retention": {"prune_interval_hours": 24}}
    policy = RetentionPolicy(store, cfg, log_dir=tmp_path / "logs")

    first = policy.maybe_run()
    assert first is not None
    second = policy.maybe_run()
    assert second is None


def test_maybe_run_writes_meta(store, tmp_path):
    cfg = {"retention": {"prune_interval_hours": 24}}
    policy = RetentionPolicy(store, cfg, log_dir=tmp_path / "logs")
    policy.maybe_run()
    assert store.get_meta("last_prune_at") is not None
