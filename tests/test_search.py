from datetime import datetime, timedelta

import pytest

from shadow.memory import MemoryStore


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "search.db"))
    yield s
    s.close()


def add_obs(
    store,
    content: str,
    source: str = "active_window",
    minutes_ago: float = 1.0,
    entity: str | None = None,
):
    ts = (datetime.utcnow() - timedelta(minutes=minutes_ago)).isoformat(
        sep=" ", timespec="seconds"
    )
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO observations (timestamp, source, content) " "VALUES (?, ?, ?)",
        (ts, source, content),
    )
    obs_id = cur.lastrowid
    if entity:
        eid = store.upsert_entity("project", entity)
        store.link_entity_to_observation(obs_id, eid)
    store.conn.commit()
    return obs_id


def test_keyword_search_matches(store):
    add_obs(store, "Working on recovery.py today")
    add_obs(store, "Reading a book")
    rows = store.search_observations(query="recovery")
    assert len(rows) == 1
    assert "recovery.py" in rows[0][3]


def test_keyword_is_case_insensitive(store):
    add_obs(store, "SHADOW project status")
    rows = store.search_observations(query="shadow")
    assert len(rows) == 1


def test_empty_query_returns_all(store):
    for i in range(3):
        add_obs(store, f"note {i}")
    rows = store.search_observations()
    assert len(rows) == 3


def test_source_filter(store):
    add_obs(store, "clipboard text", source="clipboard")
    add_obs(store, "window text", source="active_window")
    rows = store.search_observations(source="clipboard")
    assert len(rows) == 1
    assert rows[0][2] == "clipboard"


def test_entity_filter(store):
    add_obs(store, "on SHADOW", entity="SHADOW")
    add_obs(store, "on other", entity="Other")
    rows = store.search_observations(entity_name="SHADOW")
    assert len(rows) == 1
    assert "SHADOW" in rows[0][3]


def test_date_range_filter(store):
    now = datetime.utcnow()
    add_obs(store, "old", minutes_ago=60 * 24 * 10)  # 10 days ago
    add_obs(store, "new", minutes_ago=60)  # 1 hour ago

    start = (now - timedelta(days=2)).isoformat(sep=" ", timespec="seconds")
    end = now.isoformat(sep=" ", timespec="seconds")
    rows = store.search_observations(start=start, end=end)
    assert len(rows) == 1
    assert "new" in rows[0][3]


def test_combined_filters(store):
    add_obs(store, "SHADOW stuff", source="active_window", entity="SHADOW")
    add_obs(store, "SHADOW other", source="clipboard", entity="SHADOW")
    add_obs(store, "unrelated", source="active_window")

    rows = store.search_observations(
        query="SHADOW",
        source="active_window",
        entity_name="SHADOW",
    )
    assert len(rows) == 1


def test_limit_applied(store):
    for i in range(20):
        add_obs(store, f"note {i}")
    rows = store.search_observations(limit=5)
    assert len(rows) == 5


def test_ordered_newest_first(store):
    add_obs(store, "old note", minutes_ago=60)
    add_obs(store, "new note", minutes_ago=5)
    rows = store.search_observations()
    assert "new note" in rows[0][3]


def test_distinct_sources(store):
    add_obs(store, "x", source="active_window")
    add_obs(store, "y", source="clipboard")
    add_obs(store, "z", source="active_window")
    sources = store.distinct_sources()
    assert "active_window" in sources
    assert "clipboard" in sources
    assert len(sources) == 2


def test_special_chars_in_query(store):
    add_obs(store, "value is 100%")
    rows = store.search_observations(query="100%")
    # LIKE treats % as wildcard; this documents current behavior
    assert len(rows) >= 1
