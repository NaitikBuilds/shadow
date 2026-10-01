import json
from datetime import datetime, timedelta

import pytest

from shadow.agent import FocusPatternsEngine
from shadow.memory import MemoryStore


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "patterns.db"))
    yield s
    s.close()


def add_typing(
    store,
    when: datetime,
    focus_score: float,
):
    meta = json.dumps({"focus_score": focus_score})
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO observations (timestamp, source, content, metadata) "
        "VALUES (?, 'typing_dynamics', 'summary', ?)",
        (when.isoformat(sep=" ", timespec="seconds"), meta),
    )
    store.conn.commit()


def add_window(store, when: datetime, process: str, title: str = "x"):
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO observations (timestamp, source, content) "
        "VALUES (?, 'active_window', ?)",
        (when.isoformat(sep=" ", timespec="seconds"), f"{process}: {title}"),
    )
    store.conn.commit()


def test_empty_store_returns_nothing(store):
    assert FocusPatternsEngine(store).find_patterns() == []


def test_single_observation_below_min(store):
    now = datetime.utcnow() - timedelta(hours=1)
    add_typing(store, now, 0.9)
    assert FocusPatternsEngine(store).find_patterns() == []


def test_high_focus_morning_pattern(store):
    # 15 Tuesday-morning observations at 9 AM with high focus
    base = datetime.utcnow() - timedelta(days=7)
    # Align to Tuesday 9 AM
    for i in range(15):
        when = base + timedelta(minutes=4 * i)
        when = when.replace(hour=9, minute=i % 60)
        add_typing(store, when, 0.85)

    insights = FocusPatternsEngine(store).find_patterns()
    time_insights = [i for i in insights if i.kind == "focus_pattern_time"]
    assert len(time_insights) >= 1
    assert time_insights[0].score > 0


def test_low_focus_not_flagged(store):
    base = datetime.utcnow() - timedelta(days=7)
    for i in range(15):
        when = base.replace(hour=10, minute=i % 60)
        add_typing(store, when, 0.3)
    insights = FocusPatternsEngine(store).find_patterns()
    time_insights = [i for i in insights if i.kind == "focus_pattern_time"]
    assert time_insights == []


def test_process_pattern_detected(store):
    base = datetime.utcnow() - timedelta(hours=2)
    # Alternate typing + window observations
    for i in range(15):
        when = base + timedelta(minutes=i)
        add_window(store, when, "Code.exe")
        add_typing(store, when, 0.9)

    insights = FocusPatternsEngine(store).find_patterns()
    process_insights = [i for i in insights if i.kind == "focus_pattern_process"]
    assert len(process_insights) >= 1
    assert "Code" in process_insights[0].title


def test_malformed_metadata_ignored(store):
    base = datetime.utcnow() - timedelta(hours=1)
    cur = store.conn.cursor()
    for i in range(15):
        cur.execute(
            "INSERT INTO observations (timestamp, source, content, metadata) "
            "VALUES (?, 'typing_dynamics', 'x', 'not json')",
            ((base + timedelta(minutes=i)).isoformat(sep=" ", timespec="seconds"),),
        )
    store.conn.commit()
    assert FocusPatternsEngine(store).find_patterns() == []


def test_respects_limit(store):
    base = datetime.utcnow() - timedelta(days=10)
    for hour in (8, 10, 14, 16, 20):
        for i in range(15):
            when = (base + timedelta(days=i % 5)).replace(hour=hour, minute=i % 60)
            add_typing(store, when, 0.9)
    insights = FocusPatternsEngine(store).find_patterns(limit=2)
    assert len(insights) <= 2


def test_extract_focus_from_metadata():
    engine = FocusPatternsEngine.__new__(FocusPatternsEngine)
    assert engine._extract_focus(json.dumps({"focus_score": 0.75})) == 0.75
    assert engine._extract_focus(json.dumps({"other": 1})) is None
    assert engine._extract_focus(None) is None
    assert engine._extract_focus("invalid") is None
