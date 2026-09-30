from datetime import datetime, timedelta

import pytest

from shadow.agent import AmbientTaskList, SessionMemory
from shadow.memory import MemoryStore


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "ambient.db"))
    yield s
    s.close()


def add_obs(store, hours_ago: float, entity_name: str, entity_type="project"):
    ts = (datetime.utcnow() - timedelta(hours=hours_ago)).isoformat(
        sep=" ", timespec="seconds"
    )
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO observations (timestamp, source, content) "
        "VALUES (?, 'active_window', 'work')",
        (ts,),
    )
    obs_id = cur.lastrowid
    eid = store.upsert_entity(entity_type, entity_name)
    store.link_entity_to_observation(obs_id, eid)
    store.conn.commit()
    return obs_id, eid


def test_empty_store_returns_nothing(store):
    assert AmbientTaskList(store).list_active() == []


def test_recent_entity_appears(store):
    for _ in range(5):
        add_obs(store, 1, "SHADOW")
    tasks = AmbientTaskList(store).list_active()
    assert len(tasks) == 1
    assert tasks[0].name == "SHADOW"
    assert tasks[0].score > 0


def test_frequent_entity_scores_higher(store):
    for _ in range(20):
        add_obs(store, 2, "Frequent")
    for _ in range(3):
        add_obs(store, 2, "Rare")
    tasks = AmbientTaskList(store).list_active()
    names = [t.name for t in tasks]
    assert names[0] == "Frequent"


def test_recent_entity_scores_higher_than_old(store):
    for _ in range(10):
        add_obs(store, 1, "Recent")
    for _ in range(10):
        add_obs(store, 20, "Old")
    tasks = AmbientTaskList(store).list_active()
    assert tasks[0].name == "Recent"


def test_dismiss_hides_entity(store):
    for _ in range(5):
        _, eid = add_obs(store, 1, "SHADOW")
    ambient = AmbientTaskList(store)
    assert len(ambient.list_active()) == 1
    ambient.dismiss(eid)
    assert ambient.list_active() == []


def test_restore_brings_entity_back(store):
    for _ in range(5):
        _, eid = add_obs(store, 1, "SHADOW")
    ambient = AmbientTaskList(store)
    ambient.dismiss(eid)
    ambient.restore(eid)
    assert len(ambient.list_active()) == 1


def test_promoted_entity_marked(store):
    for _ in range(5):
        _, eid = add_obs(store, 1, "SHADOW")
    ambient = AmbientTaskList(store)
    ambient.promote(eid)
    tasks = ambient.list_active()
    assert len(tasks) == 1
    assert tasks[0].promoted is True


def test_file_entities_included(store):
    for _ in range(5):
        add_obs(store, 1, "recovery.py", entity_type="file")
    tasks = AmbientTaskList(store).list_active()
    assert len(tasks) == 1
    assert tasks[0].entity_type == "file"


def test_topic_entities_excluded(store):
    for _ in range(5):
        add_obs(store, 1, "Some Topic", entity_type="topic")
    tasks = AmbientTaskList(store).list_active()
    assert tasks == []


def test_max_items_respected(store):
    for i in range(20):
        for _ in range(3):
            add_obs(store, 1, f"Project{i}")
    tasks = AmbientTaskList(store).list_active()
    assert len(tasks) <= AmbientTaskList.MAX_ITEMS


def test_dismissed_list_returns_items(store):
    for _ in range(5):
        _, eid = add_obs(store, 1, "SHADOW")
    ambient = AmbientTaskList(store)
    ambient.dismiss(eid)
    dismissed = ambient.dismissed()
    assert len(dismissed) == 1
    assert dismissed[0].name == "SHADOW"


def test_session_boost_applies(store):
    # Create enough observations for a session and recent enough
    for _ in range(8):
        add_obs(store, 0.1, "SHADOW")
    session_mem = SessionMemory(store)
    ambient = AmbientTaskList(store, session_mem)
    tasks = ambient.list_active()
    assert len(tasks) >= 1
    # Score should be boosted by session membership
    assert tasks[0].score > 0.5


def test_to_dict_serializable(store):
    for _ in range(5):
        add_obs(store, 1, "SHADOW")
    tasks = AmbientTaskList(store).list_active()
    d = tasks[0].to_dict()
    assert "entity_id" in d
    assert "name" in d
    assert "score" in d
    assert d["name"] == "SHADOW"
