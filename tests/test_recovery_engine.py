from datetime import datetime, timedelta

import pytest

from shadow.agent import RecoveryEngine
from shadow.memory import MemoryStore


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "rec.db"))
    yield s
    s.close()


def add_obs(store, minutes_ago: int, entity_name: str, entity_type="project"):
    ts = (datetime.utcnow() - timedelta(minutes=minutes_ago)).isoformat(
        sep=" ", timespec="seconds"
    )
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO observations (timestamp, source, content) "
        "VALUES (?, 'test', 'work')",
        (ts,),
    )
    obs_id = cur.lastrowid
    eid = store.upsert_entity(entity_type, entity_name)
    store.link_entity_to_observation(obs_id, eid)
    store.conn.commit()
    return obs_id


def test_empty_store_returns_nothing(store):
    assert RecoveryEngine(store).find_unfinished() == []


def test_too_few_observations_not_flagged(store):
    for m in (60, 55):
        add_obs(store, m, "SHADOW")
    assert RecoveryEngine(store).find_unfinished() == []


def test_ongoing_activity_not_flagged(store):
    for m in (5, 10, 15, 20):
        add_obs(store, m, "SHADOW")
    assert RecoveryEngine(store).find_unfinished() == []


def test_unfinished_work_flagged(store):
    for m in (90, 75, 65, 60):
        add_obs(store, m, "SHADOW")
    insights = RecoveryEngine(store).find_unfinished()
    assert len(insights) == 1
    assert insights[0].kind == "recovery"
    assert "SHADOW" in insights[0].title
    assert 0.0 < insights[0].score <= 1.0


def test_multiple_projects_sorted_by_score(store):
    for m in (600, 590, 585, 580):
        add_obs(store, m, "OldProject")
    for m in (120, 100, 80, 60, 45, 30):
        add_obs(store, m, "RecentProject")

    insights = RecoveryEngine(store).find_unfinished()
    assert len(insights) == 2
    assert insights[0].title.endswith("RecentProject")


def test_returns_at_most_limit(store):
    for i in range(10):
        for m in (120 + i, 100 + i, 80 + i, 60 + i):
            add_obs(store, m, f"Project{i}")
    insights = RecoveryEngine(store).find_unfinished(limit=3)
    assert len(insights) == 3
