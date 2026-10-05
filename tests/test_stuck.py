from datetime import datetime, timedelta

import pytest

from shadow.agent import StuckDetector
from shadow.memory import MemoryStore


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "stuck.db"))
    yield s
    s.close()


def add_active_window(store, minutes_ago: float, process: str, title: str):
    ts = (datetime.utcnow() - timedelta(minutes=minutes_ago)).isoformat(
        sep=" ", timespec="seconds"
    )
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO observations (timestamp, source, content) "
        "VALUES (?, 'active_window', ?)",
        (ts, f"{process}: {title}"),
    )
    store.conn.commit()


def add_observation(store, minutes_ago: float, source: str, content: str):
    ts = (datetime.utcnow() - timedelta(minutes=minutes_ago)).isoformat(
        sep=" ", timespec="seconds"
    )
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO observations (timestamp, source, content) " "VALUES (?, ?, ?)",
        (ts, source, content),
    )
    store.conn.commit()


# ---------- Static detection ----------


def test_empty_store_returns_nothing(store):
    assert StuckDetector(store).find_stuck() == []


def test_static_window_detected(store):
    # Same title, spread over 25 minutes, ending 1 minute ago
    for m in (25, 20, 15, 10, 5, 1):
        add_active_window(store, m, "Code.exe", "recovery.py - shadow")
    insights = StuckDetector(store).find_stuck()
    kinds = {i.kind for i in insights}
    assert "stuck_static" in kinds


def test_static_window_not_triggered_without_recent_activity(store):
    # Same title but last activity 30 minutes ago (user idle)
    for m in (60, 55, 50, 45, 40, 35):
        add_active_window(store, m, "Code.exe", "recovery.py - shadow")
    insights = StuckDetector(store).find_stuck()
    kinds = {i.kind for i in insights}
    assert "stuck_static" not in kinds


def test_static_window_not_triggered_under_threshold(store):
    # Only 10 minutes span
    for m in (10, 8, 6, 4, 2, 1):
        add_active_window(store, m, "Code.exe", "recovery.py - shadow")
    insights = StuckDetector(store).find_stuck()
    kinds = {i.kind for i in insights}
    assert "stuck_static" not in kinds


def test_multiple_titles_not_static(store):
    for m in (25, 20, 15, 10, 5, 1):
        add_active_window(store, m, "Code.exe", f"file{m}.py - shadow")
    insights = StuckDetector(store).find_stuck()
    kinds = {i.kind for i in insights}
    assert "stuck_static" not in kinds


# ---------- Alternation detection ----------


def test_alternation_detected(store):
    # Alternate between two titles 10 times in 15 min
    titles = ["A - Code", "B - Chrome"]
    for i in range(10):
        add_active_window(store, 15 - i * 1.4, "app.exe", titles[i % 2])
    insights = StuckDetector(store).find_stuck()
    kinds = {i.kind for i in insights}
    assert "stuck_alternation" in kinds


def test_alternation_not_triggered_with_one_title(store):
    for i in range(10):
        add_active_window(store, 15 - i, "app.exe", "Only title")
    insights = StuckDetector(store).find_stuck()
    kinds = {i.kind for i in insights}
    assert "stuck_alternation" not in kinds


def test_alternation_not_triggered_with_three_titles(store):
    for i in range(10):
        add_active_window(store, 15 - i, "app.exe", f"Title {i % 3}")
    insights = StuckDetector(store).find_stuck()
    kinds = {i.kind for i in insights}
    assert "stuck_alternation" not in kinds


def test_alternation_not_triggered_under_threshold(store):
    # Only 4 transitions
    titles = ["A", "B", "A", "B", "A"]
    for i, t in enumerate(titles):
        add_active_window(store, 15 - i * 2, "app.exe", t)
    insights = StuckDetector(store).find_stuck()
    kinds = {i.kind for i in insights}
    assert "stuck_alternation" not in kinds


# ---------- Error detection ----------


def test_error_traceback_detected(store):
    add_observation(
        store,
        1,
        "screen_ocr",
        'Traceback (most recent call last):\n  File "test.py"...',
    )
    insights = StuckDetector(store).find_stuck()
    kinds = {i.kind for i in insights}
    assert "stuck_error" in kinds


def test_error_valueerror_detected(store):
    add_observation(store, 1, "screen_ocr", "ValueError: invalid input")
    insights = StuckDetector(store).find_stuck()
    kinds = {i.kind for i in insights}
    assert "stuck_error" in kinds


def test_error_not_detected_in_old_observations(store):
    add_observation(store, 30, "screen_ocr", "ValueError: invalid input")
    insights = StuckDetector(store).find_stuck()
    kinds = {i.kind for i in insights}
    assert "stuck_error" not in kinds


def test_error_dedupes_by_marker(store):
    # Two observations with the same marker → one insight
    add_observation(store, 2, "screen_ocr", "ValueError: one")
    add_observation(store, 1, "screen_ocr", "ValueError: two")
    insights = StuckDetector(store).find_stuck()
    error_insights = [i for i in insights if i.kind == "stuck_error"]
    assert len(error_insights) == 1


def test_no_error_marker_no_insight(store):
    add_observation(store, 1, "screen_ocr", "Just a normal paragraph")
    insights = StuckDetector(store).find_stuck()
    kinds = {i.kind for i in insights}
    assert "stuck_error" not in kinds


# ---------- Config ----------


def test_disabled_returns_nothing(store):
    detector = StuckDetector(store, {"agent": {"stuck": {"enabled": False}}})
    add_active_window(store, 1, "Code.exe", "long static title")
    add_active_window(store, 25, "Code.exe", "long static title")
    assert detector.find_stuck() == []


def test_config_helper_defaults():
    from shadow.config import stuck_config

    d = stuck_config({})
    assert d["enabled"] is True
    assert d["static_minutes"] == 20
    assert d["alternation_count"] == 8


def test_config_helper_overrides():
    from shadow.config import stuck_config

    cfg = {"agent": {"stuck": {"static_minutes": 30}}}
    d = stuck_config(cfg)
    assert d["static_minutes"] == 30
    assert d["alternation_count"] == 8
