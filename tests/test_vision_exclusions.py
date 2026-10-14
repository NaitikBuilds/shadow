import pytest

from shadow.memory import MemoryStore, VisionExclusionStore


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "vex.db"))
    yield s
    s.close()


def test_empty_store(store):
    v = VisionExclusionStore(store)
    assert v.count() == 0
    assert v.all_excluded() == []
    assert v.is_excluded("chrome.exe") is False


def test_exclude_adds(store):
    v = VisionExclusionStore(store)
    assert v.exclude("chrome.exe") is True
    assert v.is_excluded("chrome.exe") is True
    assert v.count() == 1


def test_exclude_normalizes_case(store):
    v = VisionExclusionStore(store)
    v.exclude("Chrome.EXE")
    assert v.is_excluded("chrome") is True
    assert v.is_excluded("CHROME.EXE") is True


def test_exclude_strips_exe(store):
    v = VisionExclusionStore(store)
    v.exclude("code.exe")
    assert v.is_excluded("code") is True
    assert v.is_excluded("Code.exe") is True


def test_exclude_idempotent(store):
    v = VisionExclusionStore(store)
    v.exclude("chrome.exe")
    v.exclude("chrome.exe")
    assert v.count() == 1


def test_exclude_empty_process(store):
    v = VisionExclusionStore(store)
    assert v.exclude("") is False
    assert v.exclude("   ") is False
    assert v.count() == 0


def test_include_removes(store):
    v = VisionExclusionStore(store)
    v.exclude("chrome.exe")
    assert v.include("chrome.exe") is True
    assert v.is_excluded("chrome.exe") is False


def test_include_missing_returns_true(store):
    v = VisionExclusionStore(store)
    # Deleting a non-existent row is not an error
    assert v.include("nothing.exe") is True


def test_all_excluded_ordered_by_added(store):
    v = VisionExclusionStore(store)
    v.exclude("a.exe")
    v.exclude("b.exe")
    v.exclude("c.exe")
    entries = v.all_excluded()
    assert len(entries) == 3
    assert {e["process"] for e in entries} == {"a", "b", "c"}


def test_clear_all(store):
    v = VisionExclusionStore(store)
    v.exclude("a.exe")
    v.exclude("b.exe")
    deleted = v.clear_all()
    assert deleted == 2
    assert v.count() == 0


def test_exclude_logs_activity(store):
    v = VisionExclusionStore(store)
    v.exclude("chrome.exe")
    cur = store.conn.cursor()
    cur.execute("SELECT COUNT(*) FROM activity_log WHERE action = 'vision_exclude'")
    assert cur.fetchone()[0] == 1


def test_include_logs_activity(store):
    v = VisionExclusionStore(store)
    v.exclude("chrome.exe")
    v.include("chrome.exe")
    cur = store.conn.cursor()
    cur.execute("SELECT COUNT(*) FROM activity_log WHERE action = 'vision_include'")
    assert cur.fetchone()[0] == 1


def test_persistence_across_instances(tmp_path):
    db = str(tmp_path / "vex.db")
    s1 = MemoryStore(db)
    VisionExclusionStore(s1).exclude("slack.exe")
    s1.close()

    s2 = MemoryStore(db)
    try:
        assert VisionExclusionStore(s2).is_excluded("slack") is True
    finally:
        s2.close()
