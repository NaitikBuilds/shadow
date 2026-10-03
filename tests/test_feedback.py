import pytest

from shadow.agent import FeedbackStore
from shadow.memory import MemoryStore


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "feedback.db"))
    yield s
    s.close()


def test_empty_stats_returns_one(store):
    fb = FeedbackStore(store)
    stats = fb.stats()
    assert stats.total == 0
    assert stats.rate == 1.0


def test_record_useful(store):
    fb = FeedbackStore(store)
    fb.record("recovery", "Unfinished: SHADOW", "useful")
    stats = fb.stats()
    assert stats.total == 1
    assert stats.useful == 1
    assert stats.rate == 1.0


def test_record_not_useful(store):
    fb = FeedbackStore(store)
    fb.record("decay", "Fading: old_script.py", "not_useful")
    stats = fb.stats()
    assert stats.total == 1
    assert stats.not_useful == 1
    assert stats.rate == 0.0


def test_mixed_verdicts(store):
    fb = FeedbackStore(store)
    fb.record("recovery", "A", "useful")
    fb.record("recovery", "B", "useful")
    fb.record("recovery", "C", "not_useful")
    fb.record("recovery", "D", "useful")
    stats = fb.stats()
    assert stats.total == 4
    assert stats.useful == 3
    assert stats.rate == 0.75


def test_invalid_verdict_raises(store):
    fb = FeedbackStore(store)
    with pytest.raises(ValueError):
        fb.record("recovery", "X", "maybe")


def test_empty_kind_ignored(store):
    fb = FeedbackStore(store)
    fb.record("", "X", "useful")
    assert fb.stats().total == 0


def test_verdict_for_returns_latest(store):
    fb = FeedbackStore(store)
    fb.record("recovery", "Same Title", "useful")
    fb.record("recovery", "Same Title", "not_useful")
    assert fb.verdict_for("recovery", "Same Title") == "not_useful"


def test_verdict_for_none(store):
    fb = FeedbackStore(store)
    assert fb.verdict_for("recovery", "Never Seen") is None


def test_title_hash_case_insensitive(store):
    fb = FeedbackStore(store)
    assert fb.title_hash("Hello World") == fb.title_hash("hello world")
    assert fb.title_hash("  Hello   World  ") == fb.title_hash("hello world")


def test_stats_by_kind(store):
    fb = FeedbackStore(store)
    fb.record("recovery", "A", "useful")
    fb.record("recovery", "B", "useful")
    fb.record("decay", "C", "not_useful")

    by_kind = fb.stats_by_kind()
    assert by_kind["recovery"].rate == 1.0
    assert by_kind["recovery"].total == 2
    assert by_kind["decay"].rate == 0.0
    assert by_kind["decay"].total == 1


def test_logs_activity(store):
    fb = FeedbackStore(store)
    fb.record("recovery", "Title", "useful")
    cur = store.conn.cursor()
    cur.execute("SELECT COUNT(*) FROM activity_log WHERE action = 'insight_feedback'")
    assert cur.fetchone()[0] == 1
