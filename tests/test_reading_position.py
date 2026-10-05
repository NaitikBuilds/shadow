from datetime import datetime, timedelta

import pytest

from shadow.memory import MemoryStore
from shadow.perception import (
    ReadingPositionReader,
    ReadingPositionTracker,
    UIANode,
)


def node(name="", control_type="TextControl", value="", children=None):
    return UIANode(
        name=name,
        control_type=control_type,
        value=value,
        children=children or [],
    )


# ---------- Reader ----------


def test_empty_tree_returns_zero():
    reader = ReadingPositionReader()
    pct, section = reader.extract(None)
    assert pct == 0.0
    assert section == ""


def test_vertical_scrollbar_position():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Vertical Scroll Bar", "ScrollBarControl", value="50|100"),
        ],
    )
    pct, _section = ReadingPositionReader().extract(root)
    assert pct == 50.0


def test_scrollbar_at_top():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Vertical Scroll Bar", "ScrollBarControl", value="0|100"),
        ],
    )
    pct, _ = ReadingPositionReader().extract(root)
    assert pct == 0.0


def test_scrollbar_at_bottom():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Vertical Scroll Bar", "ScrollBarControl", value="100|100"),
        ],
    )
    pct, _ = ReadingPositionReader().extract(root)
    assert pct == 100.0


def test_horizontal_scrollbar_ignored():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Horizontal Scroll Bar", "ScrollBarControl", value="50|100"),
        ],
    )
    pct, _ = ReadingPositionReader().extract(root)
    assert pct == 0.0


def test_malformed_scrollbar_value():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Vertical Scroll Bar", "ScrollBarControl", value="nonsense"),
        ],
    )
    pct, _ = ReadingPositionReader().extract(root)
    assert pct == 0.0


def test_nearest_heading_found():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Introduction", "HeadingControl"),
            node("Body text", "TextControl"),
            node("Methods", "HeadingControl"),
            node("More text", "TextControl"),
        ],
    )
    _pct, section = ReadingPositionReader().extract(root)
    # Last heading seen
    assert section == "Methods"


def test_no_headings_returns_empty():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Just body text", "TextControl"),
        ],
    )
    _pct, section = ReadingPositionReader().extract(root)
    assert section == ""


# ---------- Tracker ----------


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "reading.db"))
    yield s
    s.close()


@pytest.fixture
def config():
    return {
        "perception": {
            "reading_position": {
                "enabled": True,
                "min_change_pct": 5,
                "retention_days": 30,
            }
        }
    }


def test_record_persists_position(store, config):
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Vertical Scroll Bar", "ScrollBarControl", value="50|100"),
            node("Methods", "HeadingControl"),
        ],
    )
    tracker = ReadingPositionTracker(store, config)
    pos = tracker.record(
        process="chrome.exe",
        title="docs — https://docs.python.org/3/library/pathlib.html — Chrome",
        root=root,
    )
    assert pos is not None
    assert pos.identifier == "https://docs.python.org/3/library/pathlib.html"
    assert pos.position_pct == 50.0
    assert pos.section == "Methods"


def test_record_skips_no_identifier(store, config):
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Vertical Scroll Bar", "ScrollBarControl", value="50|100"),
        ],
    )
    tracker = ReadingPositionTracker(store, config)
    pos = tracker.record(process="someapp.exe", title="window", root=root)
    assert pos is None


def test_record_skips_small_change(store, config):
    root1 = node(
        "Root",
        "WindowControl",
        children=[
            node("Vertical Scroll Bar", "ScrollBarControl", value="50|100"),
        ],
    )
    root2 = node(
        "Root",
        "WindowControl",
        children=[
            node("Vertical Scroll Bar", "ScrollBarControl", value="52|100"),
        ],
    )

    tracker = ReadingPositionTracker(store, config)
    title = "docs — https://example.com/docs — Chrome"

    first = tracker.record("chrome.exe", title, root1)
    assert first is not None
    assert first.position_pct == 50.0

    # 2% change → below min 5%, so return existing unchanged
    second = tracker.record("chrome.exe", title, root2)
    assert second is not None
    assert second.position_pct == 50.0  # unchanged


def test_record_updates_on_large_change(store, config):
    root1 = node(
        "Root",
        "WindowControl",
        children=[
            node("Vertical Scroll Bar", "ScrollBarControl", value="50|100"),
        ],
    )
    root2 = node(
        "Root",
        "WindowControl",
        children=[
            node("Vertical Scroll Bar", "ScrollBarControl", value="80|100"),
        ],
    )

    tracker = ReadingPositionTracker(store, config)
    title = "docs — https://example.com/docs — Chrome"

    tracker.record("chrome.exe", title, root1)
    second = tracker.record("chrome.exe", title, root2)
    assert second is not None
    assert second.position_pct == 80.0


def test_get_returns_position(store, config):
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Vertical Scroll Bar", "ScrollBarControl", value="50|100"),
        ],
    )
    tracker = ReadingPositionTracker(store, config)
    tracker.record("chrome.exe", "docs — https://x.com/a — Chrome", root)
    pos = tracker.get("https://x.com/a")
    assert pos is not None
    assert pos.position_pct == 50.0


def test_get_returns_none_for_unknown(store, config):
    tracker = ReadingPositionTracker(store, config)
    assert tracker.get("https://never-seen.com") is None


def test_recent_returns_ordered(store, config):
    tracker = ReadingPositionTracker(store, config)
    for i, url in enumerate(["https://a.com", "https://b.com", "https://c.com"]):
        # Start at 10, 20, 30 — all above the "position 0" skip threshold
        root = node(
            "Root",
            "WindowControl",
            children=[
                node(
                    "Vertical Scroll Bar",
                    "ScrollBarControl",
                    value=f"{(i + 1) * 10}|100",
                ),
            ],
        )
        tracker.record("chrome.exe", f"page — {url} — Chrome", root)
    recent = tracker.recent(limit=10)
    assert len(recent) == 3


def test_resume_suggestion_text(store, config):
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Vertical Scroll Bar", "ScrollBarControl", value="62|100"),
            node("Methods", "HeadingControl"),
        ],
    )
    tracker = ReadingPositionTracker(store, config)
    tracker.record("chrome.exe", "pathlib — https://x.com/a — Chrome", root)
    text = tracker.resume_suggestion("https://x.com/a")
    assert text is not None
    assert "Methods" in text
    assert "62%" in text


def test_resume_suggestion_returns_none_for_unknown(store, config):
    tracker = ReadingPositionTracker(store, config)
    assert tracker.resume_suggestion("https://nope.com") is None


def test_prune_old_removes_stale(store, config):
    old = (datetime.utcnow() - timedelta(days=60)).isoformat(
        sep=" ", timespec="seconds"
    )
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO reading_positions "
        "(identifier, title, position_pct, section, updated_at) "
        "VALUES ('https://old.com', 'Old', 50.0, '', ?)",
        (old,),
    )
    store.conn.commit()

    tracker = ReadingPositionTracker(store, config)
    deleted = tracker.prune_old()
    assert deleted == 1


def test_disabled_tracker_noop(store):
    cfg = {"perception": {"reading_position": {"enabled": False}}}
    tracker = ReadingPositionTracker(store, cfg)
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Vertical Scroll Bar", "ScrollBarControl", value="50|100"),
        ],
    )
    pos = tracker.record("chrome.exe", "x — https://a.com — Chrome", root)
    assert pos is None


def test_config_helper_defaults():
    from shadow.config import reading_position_config

    d = reading_position_config({})
    assert d["enabled"] is True
    assert d["min_change_pct"] == 5
    assert d["retention_days"] == 30


def test_config_helper_overrides():
    from shadow.config import reading_position_config

    cfg = {"perception": {"reading_position": {"min_change_pct": 10}}}
    d = reading_position_config(cfg)
    assert d["min_change_pct"] == 10
    assert d["retention_days"] == 30
