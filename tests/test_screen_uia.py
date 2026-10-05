import sys

from shadow.perception import (
    PerceptionSource,
    ScreenUIASource,
)


def test_source_is_perception_source():
    src = ScreenUIASource()
    assert isinstance(src, PerceptionSource)


def test_metadata():
    src = ScreenUIASource()
    assert src.name == "screen_uia"
    assert src.channel == "screen_capture"
    assert src.is_screen_source is True


def test_rebuild_tree_returns_none_for_empty():
    assert ScreenUIASource._rebuild_tree(None) is None
    assert ScreenUIASource._rebuild_tree({}) is None


def test_rebuild_tree_basic():
    from shadow.perception import UIANode

    data = {
        "name": "Root",
        "control_type": "WindowControl",
        "children": [
            {"name": "Hello", "control_type": "TextControl", "children": []},
        ],
    }
    node = ScreenUIASource._rebuild_tree(data)
    assert node is not None
    assert isinstance(node, UIANode)
    assert node.name == "Root"
    assert len(node.children) == 1
    assert node.children[0].name == "Hello"


def test_rebuild_tree_preserves_fields():
    data = {
        "name": "Field",
        "control_type": "EditControl",
        "automation_id": "field1",
        "class_name": "Edit",
        "value": "hello",
        "is_password": False,
        "is_enabled": True,
        "is_selected": False,
        "is_offscreen": False,
        "bounding_rect": [10, 20, 100, 50],
        "children": [],
    }
    node = ScreenUIASource._rebuild_tree(data)
    assert node.value == "hello"
    assert node.automation_id == "field1"
    assert node.bounding_rect == (10, 20, 100, 50)


def test_sample_returns_none_on_non_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    src = ScreenUIASource()
    assert src.sample() is None


def test_self_window_skipped(monkeypatch):
    """SHADOW observing its own window returns None."""
    src = ScreenUIASource()

    class FakeWindowSource:
        @staticmethod
        def sample():
            return {
                "title": "SHADOW — Silent On-Device Life Context Agent",
                "process": "python.exe",
                "pid": 1,
                "timestamp": "2026-10-05 12:00:00",
            }

    # Patch the ActiveWindowSource class inside the screen_uia module
    import shadow.perception.screen_uia as suia_mod

    monkeypatch.setattr(suia_mod, "ActiveWindowSource", FakeWindowSource)
    assert src.sample() is None
