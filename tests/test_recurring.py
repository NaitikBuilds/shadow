from datetime import datetime, timedelta

import pytest

from shadow.agent import RecurringPatternEngine
from shadow.memory import MemoryStore


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "recurring.db"))
    yield s
    s.close()


def add_obs_at(store, when: datetime, entity_name: str, entity_type="project"):
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO observations (timestamp, source, content) "
        "VALUES (?, 'active_window', 'work')",
        (when.isoformat(sep=" ", timespec="seconds"),),
    )
    obs_id = cur.lastrowid
    eid = store.upsert_entity(entity_type, entity_name)
    store.link_entity_to_observation(obs_id, eid)
    store.conn.commit()
    return eid


def _monday_at(hour: int, weeks_ago: int) -> datetime:
    """Return a Monday at `hour` that is `weeks_ago` weeks in the past."""
    now = datetime.utcnow()
    # Find the most recent Monday
    days_since_monday = now.weekday()
    last_monday = (now - timedelta(days=days_since_monday)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )
    return last_monday - timedelta(weeks=weeks_ago)


def test_empty_store_returns_nothing(store):
    assert RecurringPatternEngine(store).find_recurring() == []


def test_single_occurrence_not_enough(store):
    add_obs_at(store, _monday_at(9, weeks_ago=1), "GitHub")
    assert RecurringPatternEngine(store).find_recurring() == []


def test_two_weeks_not_enough(store):
    for week in (1, 2):
        add_obs_at(store, _monday_at(9, weeks_ago=week), "GitHub")
    assert RecurringPatternEngine(store).find_recurring() == []


def test_three_week_monday_pattern_detected(store):
    for week in (1, 2, 3):
        add_obs_at(store, _monday_at(9, weeks_ago=week), "GitHub")
    insights = RecurringPatternEngine(store).find_recurring()
    assert len(insights) >= 1
    assert insights[0].kind == "recurring"
    assert "GitHub" in insights[0].title
    assert "Monday" in insights[0].body


def test_scattered_hours_not_a_pattern(store):
    # Three Mondays, but wildly different hours
    add_obs_at(store, _monday_at(2, weeks_ago=1), "Scattered")
    add_obs_at(store, _monday_at(10, weeks_ago=2), "Scattered")
    add_obs_at(store, _monday_at(20, weeks_ago=3), "Scattered")
    insights = RecurringPatternEngine(store).find_recurring()
    titles = [i.title for i in insights]
    assert not any("Scattered" in t for t in titles)


def test_close_hours_cluster(store):
    # Three Mondays, hours: 9, 10, 11 → within tolerance
    add_obs_at(store, _monday_at(9, weeks_ago=1), "Morning")
    add_obs_at(store, _monday_at(10, weeks_ago=2), "Morning")
    add_obs_at(store, _monday_at(11, weeks_ago=3), "Morning")
    insights = RecurringPatternEngine(store).find_recurring()
    assert any("Morning" in i.title for i in insights)


def test_file_entity_detected(store):
    for week in (1, 2, 3):
        add_obs_at(
            store,
            _monday_at(9, weeks_ago=week),
            "standup_notes.md",
            entity_type="file",
        )
    insights = RecurringPatternEngine(store).find_recurring()
    assert any("standup_notes" in i.title for i in insights)


def test_score_reflects_consistency_and_frequency(store):
    # 4 weeks of Monday 9 AM → high score
    for week in (1, 2, 3, 4):
        add_obs_at(store, _monday_at(9, weeks_ago=week), "Consistent")
    insights = RecurringPatternEngine(store).find_recurring()
    assert insights[0].score > 0.4


def test_multiple_patterns_sorted_by_score(store):
    # Strong pattern: 5 weeks, Monday 9 AM
    for week in (1, 2, 3, 4, 5):
        add_obs_at(store, _monday_at(9, weeks_ago=week), "Strong")

    # Weaker: 3 weeks, Tuesday 15 PM
    now = datetime.utcnow()
    days_since_tuesday = (now.weekday() - 1) % 7
    last_tuesday = (now - timedelta(days=days_since_tuesday)).replace(
        hour=15, minute=0, second=0, microsecond=0
    )
    for week in (1, 2, 3):
        add_obs_at(store, last_tuesday - timedelta(weeks=week), "Weaker")

    insights = RecurringPatternEngine(store).find_recurring()
    assert len(insights) >= 2
    assert "Strong" in insights[0].title


def test_respects_limit(store):
    for i in range(5):
        for week in (1, 2, 3):
            hour = 8 + i
            add_obs_at(store, _monday_at(hour, weeks_ago=week), f"Item{i}")
    insights = RecurringPatternEngine(store).find_recurring(limit=2)
    assert len(insights) <= 2


def test_topic_entity_detected(store):
    for week in (1, 2, 3):
        add_obs_at(
            store,
            _monday_at(9, weeks_ago=week),
            "Code Review",
            entity_type="topic",
        )
    insights = RecurringPatternEngine(store).find_recurring()
    assert any("Code Review" in i.title for i in insights)
