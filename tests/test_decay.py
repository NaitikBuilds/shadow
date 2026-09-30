from datetime import datetime, timedelta

import pytest

from shadow.agent import KnowledgeDecayEngine
from shadow.memory import MemoryStore


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "decay.db"))
    yield s
    s.close()


def add_entity(
    store,
    entity_type: str,
    name: str,
    mentions: int,
    days_since_last_seen: float,
):
    last_seen = (datetime.now() - timedelta(days=days_since_last_seen)).isoformat(
        sep=" ", timespec="seconds"
    )
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO entities (type, name, mention_count, last_seen) "
        "VALUES (?, ?, ?, ?)",
        (entity_type, name, mentions, last_seen),
    )
    store.conn.commit()
    return cur.lastrowid


def test_empty_store_returns_nothing(store):
    assert KnowledgeDecayEngine(store).find_decaying() == []


def test_frequently_used_recently_not_flagged(store):
    add_entity(store, "project", "Recent", mentions=20, days_since_last_seen=3)
    assert KnowledgeDecayEngine(store).find_decaying() == []


def test_fading_project_flagged(store):
    add_entity(store, "project", "OldProject", mentions=15, days_since_last_seen=45)
    insights = KnowledgeDecayEngine(store).find_decaying()
    assert len(insights) == 1
    assert insights[0].kind == "decay"
    assert "OldProject" in insights[0].title
    assert 0.0 < insights[0].score <= 1.0


def test_fading_file_flagged(store):
    add_entity(store, "file", "old_script.py", mentions=10, days_since_last_seen=30)
    insights = KnowledgeDecayEngine(store).find_decaying()
    assert len(insights) == 1
    assert "file" in insights[0].body


def test_low_mention_count_not_flagged(store):
    # Below MIN_MENTIONS (5)
    add_entity(store, "project", "Glanced", mentions=2, days_since_last_seen=60)
    assert KnowledgeDecayEngine(store).find_decaying() == []


def test_recently_touched_not_flagged(store):
    # Below MIN_STALE_DAYS (14)
    add_entity(store, "project", "Recent", mentions=50, days_since_last_seen=5)
    assert KnowledgeDecayEngine(store).find_decaying() == []


def test_topic_entities_ignored(store):
    # Only project/file are considered
    add_entity(store, "topic", "Some topic", mentions=50, days_since_last_seen=60)
    assert KnowledgeDecayEngine(store).find_decaying() == []


def test_multiple_entities_sorted_by_score(store):
    add_entity(store, "project", "SmallStale", mentions=5, days_since_last_seen=20)
    add_entity(store, "project", "BigStale", mentions=25, days_since_last_seen=60)
    insights = KnowledgeDecayEngine(store).find_decaying()
    assert insights[0].title.endswith("BigStale")


def test_respects_limit(store):
    for i in range(10):
        add_entity(store, "project", f"P{i}", mentions=10, days_since_last_seen=40)
    insights = KnowledgeDecayEngine(store).find_decaying(limit=2)
    assert len(insights) == 2
