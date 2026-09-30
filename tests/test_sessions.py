from datetime import datetime, timedelta

import pytest

from shadow.agent import SessionMemory
from shadow.memory import MemoryStore


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "sessions.db"))
    yield s
    s.close()


def add_obs(store, minutes_ago: float, content: str, entity: str | None = None):
    ts = (datetime.utcnow() - timedelta(minutes=minutes_ago)).isoformat(
        sep=" ", timespec="seconds"
    )
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO observations (timestamp, source, content) "
        "VALUES (?, 'active_window', ?)",
        (ts, content),
    )
    obs_id = cur.lastrowid
    if entity:
        eid = store.upsert_entity("project", entity)
        store.link_entity_to_observation(obs_id, eid)
    store.conn.commit()
    return obs_id


def test_empty_store_returns_nothing(store):
    assert SessionMemory(store).recent_sessions() == []


def test_continuous_session_formed(store):
    # 6 observations over 30 minutes, all SHADOW project
    for m in (30, 25, 20, 15, 10, 5):
        add_obs(store, m, "work", entity="SHADOW")
    sessions = SessionMemory(store).recent_sessions()
    assert len(sessions) == 1
    assert sessions[0].observation_count == 6
    assert sessions[0].primary_entity[1] == "SHADOW"


def test_large_gap_splits_session(store):
    # First 5 obs together, then a 60-minute gap, then 5 more
    for m in (120, 115, 110, 105, 100):
        add_obs(store, m, "work", entity="SHADOW")
    for m in (40, 35, 30, 25, 20):
        add_obs(store, m, "work", entity="SHADOW")
    sessions = SessionMemory(store).recent_sessions()
    assert len(sessions) == 2


def test_no_shared_entity_splits_session(store):
    # Two 5-observation runs within 10 min but with different entities
    for m in (10, 9, 8, 7, 6):
        add_obs(store, m, "work", entity="ProjectA")
    for m in (5, 4, 3, 2, 1):
        add_obs(store, m, "work", entity="ProjectB")
    sessions = SessionMemory(store).recent_sessions()
    assert len(sessions) == 2


def test_below_min_observations_ignored(store):
    # Only 3 observations
    for m in (10, 8, 6):
        add_obs(store, m, "work", entity="SHADOW")
    assert SessionMemory(store).recent_sessions() == []


def test_most_recent_first(store):
    for m in (600, 595, 590, 585, 580):
        add_obs(store, m, "older", entity="Old")
    for m in (30, 25, 20, 15, 10):
        add_obs(store, m, "newer", entity="New")
    sessions = SessionMemory(store).recent_sessions()
    assert sessions[0].primary_entity[1] == "New"


def test_duration_calculated(store):
    for m in (30, 25, 20, 15, 10, 5):
        add_obs(store, m, "work", entity="SHADOW")
    sessions = SessionMemory(store).recent_sessions()
    # 30 - 5 = 25 min span
    assert 24.0 <= sessions[0].duration_min <= 26.0


def test_session_id_is_deterministic(store):
    for m in (30, 25, 20, 15, 10, 5):
        add_obs(store, m, "work", entity="SHADOW")
    s1 = SessionMemory(store).recent_sessions()[0]
    s2 = SessionMemory(store).recent_sessions()[0]
    assert s1.session_id == s2.session_id


def test_current_session_returns_recent(store):
    # Session ending 5 minutes ago
    for m in (40, 35, 30, 25, 20, 15, 10, 5):
        add_obs(store, m, "work", entity="SHADOW")
    current = SessionMemory(store).current_session()
    assert current is not None
    assert current.primary_entity[1] == "SHADOW"


def test_current_session_none_when_stale(store):
    # Session ending 60 minutes ago
    for m in (120, 115, 110, 105, 100, 95):
        add_obs(store, m, "work", entity="SHADOW")
    current = SessionMemory(store).current_session()
    assert current is None


def test_resume_summary_contains_entity(store):
    for m in (30, 25, 20, 15, 10, 5):
        add_obs(store, m, "work", entity="SHADOW")
    session = SessionMemory(store).recent_sessions()[0]
    summary = SessionMemory(store).resume_summary(session)
    assert "SHADOW" in summary
    assert "observations" in summary


def test_to_dict_serializable(store):
    for m in (30, 25, 20, 15, 10, 5):
        add_obs(store, m, "work", entity="SHADOW")
    session = SessionMemory(store).recent_sessions()[0]
    d = session.to_dict()
    assert d["session_id"]
    assert d["start"]
    assert d["end"]
    assert d["observation_count"] == 6
    assert d["primary_entity"]["name"] == "SHADOW"


def test_observations_without_entities_ignored(store):
    # All 6 observations have no entity
    for m in (30, 25, 20, 15, 10, 5):
        add_obs(store, m, "work")  # no entity
    assert SessionMemory(store).recent_sessions() == []
