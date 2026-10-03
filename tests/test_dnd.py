import pytest

from shadow.agent import DoNotDisturb
from shadow.memory import MemoryStore


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "dnd.db"))
    yield s
    s.close()


def test_dnd_defaults_off(store):
    dnd = DoNotDisturb(store)
    assert dnd.enabled is False


def test_dnd_toggle(store):
    dnd = DoNotDisturb(store)
    assert dnd.toggle() is True
    assert dnd.enabled is True
    assert dnd.toggle() is False
    assert dnd.enabled is False


def test_dnd_persists_across_instances(store):
    dnd1 = DoNotDisturb(store)
    dnd1.set(True)

    dnd2 = DoNotDisturb(store)
    assert dnd2.enabled is True


def test_dnd_set_idempotent(store):
    dnd = DoNotDisturb(store)
    dnd.set(True)
    dnd.set(True)
    assert dnd.enabled is True


def test_dnd_emits_changed_signal(store):
    received = []
    dnd = DoNotDisturb(store)
    dnd.changed.connect(received.append)

    dnd.set(True)
    dnd.set(False)

    assert received == [True, False]


def test_dnd_no_signal_on_noop(store):
    received = []
    dnd = DoNotDisturb(store)
    dnd.changed.connect(received.append)

    dnd.set(False)  # already False
    assert received == []


def test_dnd_logs_activity(store):
    dnd = DoNotDisturb(store)
    dnd.set(True)

    cur = store.conn.cursor()
    cur.execute("SELECT COUNT(*) FROM activity_log WHERE action = 'dnd_change'")
    assert cur.fetchone()[0] == 1
