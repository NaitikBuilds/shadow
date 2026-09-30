from datetime import datetime, timedelta

import pytest

from shadow.agent import ForecastingEngine
from shadow.memory import MemoryStore


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "forecast.db"))
    yield s
    s.close()


def add_observation(
    store, minutes_ago: int, source: str, content: str, metadata: str = ""
):
    ts = (datetime.now() - timedelta(minutes=minutes_ago)).isoformat(
        sep=" ", timespec="seconds"
    )
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO observations (timestamp, source, content, metadata) "
        "VALUES (?, ?, ?, ?)",
        (ts, source, content, metadata),
    )
    store.conn.commit()
    return cur.lastrowid


def test_empty_store_returns_nothing(store):
    assert ForecastingEngine(store).forecast() == []


def test_upcoming_calendar_event_flagged(store):
    start = datetime.now() + timedelta(minutes=20)
    content = (
        f"Calendar event (upcoming): Team standup "
        f"from {start.strftime('%Y-%m-%d %H:%M')} "
        f"to {(start + timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M')}"
    )
    add_observation(store, 1, "calendar", content)

    insights = ForecastingEngine(store).forecast()
    assert any("Team standup" in i.title for i in insights)
    assert any(i.kind == "forecast_calendar" for i in insights)


def test_far_calendar_event_not_flagged(store):
    start = datetime.now() + timedelta(hours=5)
    content = (
        f"Calendar event (upcoming): Later event "
        f"from {start.strftime('%Y-%m-%d %H:%M')} "
        f"to {(start + timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M')}"
    )
    add_observation(store, 1, "calendar", content)

    insights = ForecastingEngine(store).forecast()
    assert not any("Later event" in i.title for i in insights)


def test_session_continuity_flagged(store):
    for m in (2, 5, 8, 12):
        obs_id = add_observation(store, m, "active_window", "work")
        eid = store.upsert_entity("project", "SHADOW")
        store.link_entity_to_observation(obs_id, eid)

    insights = ForecastingEngine(store).forecast()
    session = [i for i in insights if i.kind == "forecast_session"]
    assert len(session) == 1
    assert "SHADOW" in session[0].title


def test_low_session_count_not_flagged(store):
    obs_id = add_observation(store, 5, "active_window", "work")
    eid = store.upsert_entity("project", "SHADOW")
    store.link_entity_to_observation(obs_id, eid)

    insights = ForecastingEngine(store).forecast()
    assert not any(i.kind == "forecast_session" for i in insights)


def test_calendar_parsing_handles_malformed(store):
    add_observation(store, 1, "calendar", "not a real calendar observation")
    # Should not raise
    assert isinstance(ForecastingEngine(store).forecast(), list)


def test_dedupes_by_title(store):
    start = datetime.now() + timedelta(minutes=15)
    content = (
        f"Calendar event (upcoming): Meeting "
        f"from {start.strftime('%Y-%m-%d %H:%M')} "
        f"to {(start + timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M')}"
    )
    add_observation(store, 2, "calendar", content)
    add_observation(store, 1, "calendar", content)

    insights = ForecastingEngine(store).forecast()
    titles = [i.title for i in insights]
    assert len(titles) == len(set(titles))
