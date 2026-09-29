
import pytest

from shadow.memory import MemoryStore


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "kg.db"), vector_dim=384)
    yield s
    s.close()


def test_upsert_entity_creates(store):
    eid = store.upsert_entity("project", "SHADOW")
    ent = store.entity_by_name("project", "SHADOW")
    assert ent is not None
    assert ent["id"] == eid
    assert ent["type"] == "project"
    assert ent["name"] == "SHADOW"
    assert ent["mention_count"] == 1


def test_upsert_entity_bumps_count(store):
    store.upsert_entity("project", "SHADOW")
    store.upsert_entity("project", "SHADOW")
    store.upsert_entity("project", "SHADOW")
    ent = store.entity_by_name("project", "SHADOW")
    assert ent["mention_count"] == 3


def test_upsert_entity_rejects_empty(store):
    with pytest.raises(ValueError):
        store.upsert_entity("project", "   ")


def test_link_entity_to_observation(store):
    obs_id = store.add_observation("test", "Working on SHADOW today")
    eid = store.upsert_entity("project", "SHADOW")
    store.link_entity_to_observation(obs_id, eid)
    linked = store.entities_for_observation(obs_id)
    assert len(linked) == 1
    assert linked[0]["name"] == "SHADOW"


def test_link_is_idempotent(store):
    obs_id = store.add_observation("test", "SHADOW")
    eid = store.upsert_entity("project", "SHADOW")
    store.link_entity_to_observation(obs_id, eid)
    store.link_entity_to_observation(obs_id, eid)
    linked = store.entities_for_observation(obs_id)
    assert len(linked) == 1


def test_add_edge_and_neighbors(store):
    a = store.upsert_entity("person", "Naitik")
    b = store.upsert_entity("project", "SHADOW")
    store.add_edge(a, b, "works_on", weight=1.0)

    neighbors = store.neighbors(a)
    assert len(neighbors) == 1
    assert neighbors[0]["name"] == "SHADOW"
    assert neighbors[0]["relation"] == "works_on"
    assert neighbors[0]["direction"] == "out"


def test_edge_weight_accumulates(store):
    a = store.upsert_entity("person", "Naitik")
    b = store.upsert_entity("project", "SHADOW")
    store.add_edge(a, b, "works_on", weight=1.0)
    store.add_edge(a, b, "works_on", weight=1.0)
    store.add_edge(a, b, "works_on", weight=0.5)

    neighbors = store.neighbors(a)
    assert len(neighbors) == 1
    assert neighbors[0]["weight"] == pytest.approx(2.5)


def test_self_edge_ignored(store):
    a = store.upsert_entity("person", "Naitik")
    store.add_edge(a, a, "is_self")
    assert store.neighbors(a) == []


def test_recent_entities(store):
    store.upsert_entity("project", "SHADOW")
    store.upsert_entity("person", "Naitik")
    recent = store.recent_entities()
    names = {e["name"] for e in recent}
    assert "SHADOW" in names
    assert "Naitik" in names


def test_wipe_clears_graph(store):
    obs_id = store.add_observation("test", "SHADOW")
    a = store.upsert_entity("person", "Naitik")
    b = store.upsert_entity("project", "SHADOW")
    store.link_entity_to_observation(obs_id, b)
    store.add_edge(a, b, "works_on")

    store.wipe()

    assert store.recent_entities() == []
    assert store.neighbors(a) == []
