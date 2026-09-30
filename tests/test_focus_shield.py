import json
from datetime import datetime, timedelta

import pytest

from shadow.agent import FocusShield, FocusState, Insight
from shadow.memory import MemoryStore


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "focus.db"))
    yield s
    s.close()


def add_typing(store, minutes_ago: float, focus_score: float):
    ts = (datetime.now() - timedelta(minutes=minutes_ago)).isoformat(
        sep=" ", timespec="seconds"
    )
    meta = json.dumps({"focus_score": focus_score})
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO observations (timestamp, source, content, metadata) "
        "VALUES (?, 'typing_dynamics', 'summary', ?)",
        (ts, meta),
    )
    store.conn.commit()


def test_no_typing_rows_is_normal(store):
    assert FocusShield(store).current_state() == FocusState.NORMAL


def test_deep_focus_detected(store):
    for m in (1, 3, 5, 7):
        add_typing(store, m, 0.85)
    assert FocusShield(store).current_state() == FocusState.FOCUSED


def test_low_focus_is_normal(store):
    for m in (1, 3, 5, 7):
        add_typing(store, m, 0.3)
    assert FocusShield(store).current_state() == FocusState.NORMAL


def test_idle_after_no_activity(store):
    add_typing(store, 30, 0.9)
    assert FocusShield(store).current_state() == FocusState.IDLE


def test_no_metadata_is_ignored(store):
    ts = datetime.now().isoformat(sep=" ", timespec="seconds")
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO observations (timestamp, source, content) "
        "VALUES (?, 'typing_dynamics', 'x')",
        (ts,),
    )
    store.conn.commit()
    assert FocusShield(store).current_state() == FocusState.NORMAL


def test_malformed_metadata_is_ignored(store):
    ts = datetime.now().isoformat(sep=" ", timespec="seconds")
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO observations (timestamp, source, content, metadata) "
        "VALUES (?, 'typing_dynamics', 'x', 'not json')",
        (ts,),
    )
    store.conn.commit()
    assert FocusShield(store).current_state() == FocusState.NORMAL


def test_filter_removes_low_score_when_focused(store):
    for m in (1, 3, 5):
        add_typing(store, m, 0.9)
    shield = FocusShield(store)

    insights = [
        Insight(kind="recovery", title="A", body="a", score=0.95),
        Insight(kind="recovery", title="B", body="b", score=0.5),
        Insight(kind="recovery", title="C", body="c", score=0.4),
    ]
    kept = shield.filter(insights)
    assert len(kept) == 1
    assert kept[0].title == "A"


def test_filter_passes_through_when_normal(store):
    shield = FocusShield(store)
    insights = [
        Insight(kind="recovery", title="A", body="a", score=0.3),
        Insight(kind="recovery", title="B", body="b", score=0.2),
    ]
    assert len(shield.filter(insights)) == 2


def test_should_notify_false_when_idle(store):
    add_typing(store, 30, 0.9)
    assert FocusShield(store).should_notify() is False


def test_should_notify_true_when_focused(store):
    for m in (1, 3, 5):
        add_typing(store, m, 0.9)
    assert FocusShield(store).should_notify() is True


def test_weighted_focus_favors_recent(store):
    add_typing(store, 9, 0.1)
    add_typing(store, 7, 0.1)
    add_typing(store, 3, 0.9)
    add_typing(store, 1, 0.9)
    # recent high scores outweigh older low scores
    assert FocusShield(store).current_state() == FocusState.FOCUSED
