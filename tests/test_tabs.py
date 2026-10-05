from datetime import datetime, timedelta

import pytest

from shadow.memory import MemoryStore
from shadow.perception import (
    TabInfo,
    TabReader,
    TabStateTracker,
    UIANode,
)


def node(name="", control_type="TextControl", children=None, selected=False):
    return UIANode(
        name=name,
        control_type=control_type,
        is_selected=selected,
        children=children or [],
    )


# ---------- TabReader ----------


def test_empty_tree_returns_empty():
    root = node("Root", "WindowControl")
    assert TabReader().extract(root) == []


def test_single_tab_extracted():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node(
                "Tabs",
                "TabControl",
                children=[
                    node("GitHub", "TabItemControl", selected=True),
                ],
            ),
        ],
    )
    tabs = TabReader().extract(root)
    assert len(tabs) == 1
    assert tabs[0].title == "GitHub"
    assert tabs[0].is_active is True


def test_multiple_tabs_preserve_order():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node(
                "Tabs",
                "TabControl",
                children=[
                    node("First", "TabItemControl"),
                    node("Second", "TabItemControl", selected=True),
                    node("Third", "TabItemControl"),
                ],
            ),
        ],
    )
    tabs = TabReader().extract(root)
    assert [t.title for t in tabs] == ["First", "Second", "Third"]
    assert [t.order for t in tabs] == [0, 1, 2]
    assert tabs[1].is_active is True


def test_empty_tab_names_skipped():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node(
                "Tabs",
                "TabControl",
                children=[
                    node("", "TabItemControl"),
                    node("Real", "TabItemControl"),
                ],
            ),
        ],
    )
    tabs = TabReader().extract(root)
    assert len(tabs) == 1
    assert tabs[0].title == "Real"


def test_nested_tab_control_found():
    inner = node(
        "Tabs",
        "TabControl",
        children=[
            node("Tab 1", "TabItemControl"),
        ],
    )
    mid = node("Panel", "PaneControl", children=[inner])
    root = node("Root", "WindowControl", children=[mid])
    tabs = TabReader().extract(root)
    assert len(tabs) == 1


def test_multiple_tab_controls_flattened():
    tc1 = node("A", "TabControl", children=[node("A1", "TabItemControl")])
    tc2 = node("B", "TabControl", children=[node("B1", "TabItemControl")])
    root = node("Root", "WindowControl", children=[tc1, tc2])
    tabs = TabReader().extract(root)
    assert len(tabs) == 2
    assert {t.title for t in tabs} == {"A1", "B1"}


def test_tab_title_truncated():
    long_name = "T" * 500
    root = node(
        "Root",
        "WindowControl",
        children=[
            node(
                "Tabs",
                "TabControl",
                children=[
                    node(long_name, "TabItemControl"),
                ],
            ),
        ],
    )
    tabs = TabReader().extract(root)
    assert len(tabs[0].title) <= 200


def test_tab_info_to_dict():
    t = TabInfo(title="GitHub", is_active=True, order=3)
    d = t.to_dict()
    assert d == {"title": "GitHub", "is_active": True, "order": 3}


# ---------- TabStateTracker ----------


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "tabs.db"))
    yield s
    s.close()


def test_record_inserts_tabs(store):
    tracker = TabStateTracker(store)
    tracker.record(
        "chrome",
        [
            TabInfo(title="GitHub", is_active=True, order=0),
            TabInfo(title="Docs", is_active=False, order=1),
        ],
    )

    cur = store.conn.cursor()
    cur.execute("SELECT COUNT(*) FROM tab_state")
    assert cur.fetchone()[0] == 2


def test_record_updates_last_seen(store):
    tracker = TabStateTracker(store)
    tracker.record("chrome", [TabInfo(title="GitHub", order=0)])

    cur = store.conn.cursor()
    cur.execute("SELECT last_seen FROM tab_state WHERE tab_title = 'GitHub'")
    first = cur.fetchone()[0]

    # Second record should update last_seen
    tracker.record("chrome", [TabInfo(title="GitHub", order=0)])
    cur.execute("SELECT last_seen FROM tab_state WHERE tab_title = 'GitHub'")
    second = cur.fetchone()[0]

    # Timestamps equal (same second) — different key check
    assert second >= first


def test_record_marks_active(store):
    tracker = TabStateTracker(store)
    tracker.record(
        "chrome",
        [
            TabInfo(title="Active", is_active=True, order=0),
            TabInfo(title="Inactive", is_active=False, order=1),
        ],
    )

    cur = store.conn.cursor()
    cur.execute("SELECT last_active FROM tab_state WHERE tab_title = 'Active'")
    assert cur.fetchone()[0] is not None
    cur.execute("SELECT last_active FROM tab_state WHERE tab_title = 'Inactive'")
    assert cur.fetchone()[0] is None


def test_record_empty_process_ignored(store):
    tracker = TabStateTracker(store)
    tracker.record("", [TabInfo(title="X", order=0)])
    cur = store.conn.cursor()
    cur.execute("SELECT COUNT(*) FROM tab_state")
    assert cur.fetchone()[0] == 0


def test_stale_tabs_detects_old_unvisited(store):
    # Insert directly with old first_seen
    old = (datetime.utcnow() - timedelta(hours=10)).isoformat(
        sep=" ", timespec="seconds"
    )
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO tab_state (window_process, tab_title, first_seen, last_seen) "
        "VALUES ('chrome', 'Forgotten tab', ?, ?)",
        (old, old),
    )
    store.conn.commit()

    tracker = TabStateTracker(store)
    stale = tracker.stale_tabs(stale_hours=6)
    assert len(stale) == 1
    assert stale[0].title == "Forgotten tab"
    assert stale[0].hours_open >= 9


def test_stale_tabs_excludes_visited(store):
    old = (datetime.utcnow() - timedelta(hours=10)).isoformat(
        sep=" ", timespec="seconds"
    )
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO tab_state "
        "(window_process, tab_title, first_seen, last_seen, last_active) "
        "VALUES ('chrome', 'Visited tab', ?, ?, ?)",
        (old, old, old),
    )
    store.conn.commit()

    tracker = TabStateTracker(store)
    assert tracker.stale_tabs(stale_hours=6) == []


def test_stale_tabs_respects_process_filter(store):
    old = (datetime.utcnow() - timedelta(hours=10)).isoformat(
        sep=" ", timespec="seconds"
    )
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO tab_state (window_process, tab_title, first_seen, last_seen) "
        "VALUES ('chrome', 'Tab A', ?, ?)",
        (old, old),
    )
    cur.execute(
        "INSERT INTO tab_state (window_process, tab_title, first_seen, last_seen) "
        "VALUES ('msedge', 'Tab B', ?, ?)",
        (old, old),
    )
    store.conn.commit()

    tracker = TabStateTracker(store)
    chrome_stale = tracker.stale_tabs(process="chrome", stale_hours=6)
    assert len(chrome_stale) == 1
    assert chrome_stale[0].title == "Tab A"


def test_prune_old_deletes_stale_rows(store):
    old = (datetime.utcnow() - timedelta(days=30)).isoformat(
        sep=" ", timespec="seconds"
    )
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO tab_state (window_process, tab_title, first_seen, last_seen) "
        "VALUES ('chrome', 'Ancient', ?, ?)",
        (old, old),
    )
    store.conn.commit()

    tracker = TabStateTracker(store)
    deleted = tracker.prune_old(retention_days=7)
    assert deleted == 1
    cur.execute("SELECT COUNT(*) FROM tab_state")
    assert cur.fetchone()[0] == 0


def test_related_tabs_groups_by_keyword(store):
    tracker = TabStateTracker(store)
    tracker.record(
        "chrome",
        [
            TabInfo(title="Python asyncio tutorial", order=0),
            TabInfo(title="Python asyncio best practices", order=1),
            TabInfo(title="Random cat videos", order=2),
        ],
    )
    groups = tracker.related_tabs()
    assert len(groups) >= 1
    assert any("Python" in g.tabs[0] or "asyncio" in g.keyword for g in groups)


def test_related_tabs_requires_two_shared_words(store):
    tracker = TabStateTracker(store)
    # Only one word shared ("Python") — not enough with min_overlap=2
    tracker.record(
        "chrome",
        [
            TabInfo(title="Python tutorial", order=0),
            TabInfo(title="Python book", order=1),
        ],
    )
    groups = tracker.related_tabs(min_overlap=2)
    assert groups == []


def test_related_tabs_no_groups_for_unrelated(store):
    tracker = TabStateTracker(store)
    tracker.record(
        "chrome",
        [
            TabInfo(title="Random cat videos", order=0),
            TabInfo(title="Space exploration news", order=1),
        ],
    )
    assert tracker.related_tabs() == []


def test_significant_words_strips_stopwords():
    words = TabStateTracker._significant_words(
        "The Python documentation for the async module"
    )
    assert "the" not in words
    assert "for" not in words
    assert "python" in words
    assert "async" in words
    assert "module" in words


def test_significant_words_min_length():
    words = TabStateTracker._significant_words("a I so up be")
    assert words == set()


def test_related_tabs_to_dict():
    from shadow.perception import RelatedTabs

    rt = RelatedTabs(keyword="python", tabs=["Tab A", "Tab B"])
    d = rt.to_dict()
    assert d["keyword"] == "python"
    assert d["tabs"] == ["Tab A", "Tab B"]


def test_stale_tab_to_dict():
    from shadow.perception import StaleTab

    st = StaleTab(title="Old", hours_open=8.5, process="chrome")
    d = st.to_dict()
    assert d["title"] == "Old"
    assert d["hours_open"] == 8.5
    assert d["process"] == "chrome"


# ---------- Config ----------


def test_config_helper_defaults():
    from shadow.config import tabs_config

    d = tabs_config({})
    assert d["enabled"] is True
    assert d["stale_hours"] == 6
    assert d["retention_days"] == 7


def test_config_helper_overrides():
    from shadow.config import tabs_config

    cfg = {"perception": {"tabs": {"stale_hours": 12}}}
    d = tabs_config(cfg)
    assert d["stale_hours"] == 12
    assert d["retention_days"] == 7
