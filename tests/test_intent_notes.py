from datetime import datetime, timedelta

import pytest

from shadow.agent import IntentNotesEngine
from shadow.memory import MemoryStore


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "intent.db"))
    yield s
    s.close()


def add_obs(store, content: str, minutes_ago: float = 1.0):
    ts = (datetime.utcnow() - timedelta(minutes=minutes_ago)).isoformat(
        sep=" ", timespec="seconds"
    )
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO observations (timestamp, source, content) "
        "VALUES (?, 'active_window', ?)",
        (ts, content),
    )
    store.conn.commit()


def test_empty_store_returns_nothing(store):
    assert IntentNotesEngine(store).find_notes() == []


def test_note_to_self_detected(store):
    add_obs(store, "Working on code. Note to self: ask Priya about the API.")
    insights = IntentNotesEngine(store).find_notes()
    assert len(insights) == 1
    assert insights[0].kind == "intent_note"
    assert "ask Priya" in insights[0].body


def test_remind_me_detected(store):
    add_obs(store, "Remind me to send the report by Friday.")
    insights = IntentNotesEngine(store).find_notes()
    assert len(insights) == 1
    assert "send the report" in insights[0].body


def test_dont_forget_detected(store):
    add_obs(store, "Don't forget to back up the database tonight.")
    insights = IntentNotesEngine(store).find_notes()
    assert len(insights) == 1
    assert "back up the database" in insights[0].body


def test_i_need_to_detected(store):
    add_obs(store, "I need to review the security policy changes.")
    insights = IntentNotesEngine(store).find_notes()
    assert len(insights) == 1


def test_case_insensitive(store):
    add_obs(store, "NOTE TO SELF: schedule the dentist.")
    insights = IntentNotesEngine(store).find_notes()
    assert len(insights) == 1


def test_multiple_intents_in_one_observation(store):
    add_obs(
        store,
        "Note to self: water plants. Remind me to call mom.",
    )
    insights = IntentNotesEngine(store).find_notes()
    assert len(insights) == 2


def test_duplicate_suppressed(store):
    add_obs(store, "Note to self: buy groceries.", minutes_ago=5)
    add_obs(store, "Note to self: buy groceries.", minutes_ago=1)
    insights = IntentNotesEngine(store).find_notes()
    assert len(insights) == 1


def test_old_observation_ignored(store):
    add_obs(store, "Note to self: old thing.", minutes_ago=48 * 60)
    assert IntentNotesEngine(store).find_notes() == []


def test_short_action_ignored(store):
    add_obs(store, "Note to self: a")
    insights = IntentNotesEngine(store).find_notes()
    assert insights == []


def test_respects_limit(store):
    for i in range(10):
        add_obs(store, f"Note to self: unique thing {i}.")
    insights = IntentNotesEngine(store).find_notes(limit=3)
    assert len(insights) == 3


def test_bypass_focus_shield_set(store):
    add_obs(store, "Remind me to water the plants.")
    insights = IntentNotesEngine(store).find_notes()
    assert insights[0].bypass_focus_shield is True
