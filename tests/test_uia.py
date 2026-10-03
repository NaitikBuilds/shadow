from shadow.perception import PerceptionSource, UIANode, UIAutomationSource


class FakeControl:
    """Minimal mock that satisfies the UIA walker interface."""

    def __init__(
        self,
        name: str = "",
        control_type: str = "TextControl",
        automation_id: str = "",
        class_name: str = "",
        is_password: bool = False,
        is_enabled: bool = True,
        is_offscreen: bool = False,
        rect=(0, 0, 100, 20),
        children=None,
    ):
        self.Name = name
        self.ControlTypeName = control_type
        self.AutomationId = automation_id
        self.ClassName = class_name
        self.IsPassword = is_password
        self.IsEnabled = is_enabled
        self.IsOffscreen = is_offscreen

        # BoundingRectangle is an object with left/top/right/bottom attrs
        class _R:
            pass

        r = _R()
        r.left, r.top, r.right, r.bottom = rect
        self.BoundingRectangle = r

        self._children = children or []

    def GetChildren(self):
        return self._children


def test_source_is_perception_source():
    assert isinstance(UIAutomationSource(), PerceptionSource)


def test_metadata():
    src = UIAutomationSource()
    assert src.name == "screen_uia"
    assert src.channel == "screen_capture"


def test_uia_node_to_dict_roundtrip():
    node = UIANode(
        name="Save",
        control_type="ButtonControl",
        automation_id="saveBtn",
    )
    d = node.to_dict()
    assert d["name"] == "Save"
    assert d["control_type"] == "ButtonControl"
    assert d["automation_id"] == "saveBtn"
    assert d["children"] == []


def test_uia_node_is_textual_true():
    node = UIANode(name="hello", control_type="TextControl")
    assert node.is_textual() is True


def test_uia_node_is_textual_false_when_empty():
    node = UIANode(name="", control_type="TextControl")
    assert node.is_textual() is False


def test_uia_node_is_textual_true_when_button():
    # Buttons carry labels we want to extract
    node = UIANode(name="Save", control_type="ButtonControl")
    assert node.is_textual() is True


def test_uia_node_is_textual_false_when_unknown():
    node = UIANode(name="x", control_type="ImageControl")
    assert node.is_textual() is False


def test_walk_basic_tree():
    src = UIAutomationSource(max_depth=5, max_elements=100)
    root = FakeControl(
        name="Root",
        control_type="WindowControl",
        children=[
            FakeControl(name="Hello", control_type="TextControl"),
            FakeControl(name="Save", control_type="ButtonControl"),
        ],
    )
    node = src._walk(root, depth=0)
    assert node is not None
    assert node.name == "Root"
    assert len(node.children) == 2
    assert node.children[0].name == "Hello"
    assert node.children[1].name == "Save"


def test_walk_respects_depth_limit():
    # max_depth=1 → only root + 1 level of children
    src = UIAutomationSource(max_depth=1, max_elements=100)
    deep = FakeControl(name="L3", control_type="TextControl")
    mid = FakeControl(name="L2", control_type="TextControl", children=[deep])
    root = FakeControl(name="L1", control_type="TextControl", children=[mid])

    node = src._walk(root, depth=0)
    assert node is not None
    assert node.name == "L1"
    assert len(node.children) == 1
    assert node.children[0].name == "L2"
    # L3 at depth=2 exceeds max_depth=1 → dropped
    assert len(node.children[0].children) == 0


def test_walk_allows_depth_up_to_limit():
    # max_depth=2 → root + L2 + L3 all included
    src = UIAutomationSource(max_depth=2, max_elements=100)
    deep = FakeControl(name="L3", control_type="TextControl")
    mid = FakeControl(name="L2", control_type="TextControl", children=[deep])
    root = FakeControl(name="L1", control_type="TextControl", children=[mid])

    node = src._walk(root, depth=0)
    assert node is not None
    assert len(node.children) == 1
    assert len(node.children[0].children) == 1
    assert node.children[0].children[0].name == "L3"


def test_walk_respects_element_cap():
    src = UIAutomationSource(max_depth=10, max_elements=5)
    # Build a root with 10 children
    children = [
        FakeControl(name=f"child{i}", control_type="TextControl") for i in range(10)
    ]
    root = FakeControl(name="Root", control_type="WindowControl", children=children)
    node = src._walk(root, depth=0)
    assert node is not None
    # 1 (root) + 4 children (cap = 5) = 5 nodes total
    assert src._element_count <= 5
    assert len(node.children) <= 4


def test_password_field_excluded():
    src = UIAutomationSource()
    password = FakeControl(
        name="secret",
        control_type="EditControl",
        is_password=True,
    )
    root = FakeControl(
        name="Form",
        control_type="WindowControl",
        children=[
            FakeControl(name="Username", control_type="EditControl"),
            password,
            FakeControl(name="Submit", control_type="ButtonControl"),
        ],
    )
    node = src._walk(root, depth=0)
    assert node is not None
    assert len(node.children) == 2  # password skipped
    names = [c.name for c in node.children]
    assert "secret" not in names


def test_password_children_also_excluded():
    """Children of password fields should also be skipped."""
    src = UIAutomationSource()
    inner = FakeControl(name="inner_secret", control_type="TextControl")
    password = FakeControl(
        name="password",
        control_type="EditControl",
        is_password=True,
        children=[inner],
    )
    root = FakeControl(
        name="Root",
        control_type="WindowControl",
        children=[password],
    )
    node = src._walk(root, depth=0)
    assert node is not None
    assert len(node.children) == 0


def test_offscreen_element_excluded():
    src = UIAutomationSource()
    root = FakeControl(
        name="Root",
        control_type="WindowControl",
        children=[
            FakeControl(name="visible", control_type="TextControl"),
            FakeControl(
                name="offscreen", control_type="TextControl", is_offscreen=True
            ),
        ],
    )
    node = src._walk(root, depth=0)
    assert node is not None
    assert len(node.children) == 1
    assert node.children[0].name == "visible"


def test_count_nodes():
    node = UIANode(
        name="root",
        control_type="WindowControl",
        children=[
            UIANode(name="a", control_type="TextControl"),
            UIANode(
                name="b",
                control_type="TextControl",
                children=[UIANode(name="c", control_type="TextControl")],
            ),
        ],
    )
    assert UIAutomationSource._count_nodes(node) == 4


def test_walk_handles_missing_attributes():
    """A control with missing attributes shouldn't crash the walker."""

    class Bare:
        Name = None
        ControlTypeName = None
        AutomationId = None
        ClassName = None
        IsPassword = None
        IsEnabled = None
        IsOffscreen = None
        BoundingRectangle = None

        def GetChildren(self):
            return []

    src = UIAutomationSource()
    node = src._walk(Bare(), depth=0)
    # Should still return a node (empty strings) or None if all fail
    # Our implementation returns a node with empty name
    assert node is None or node.name == ""


def test_sample_returns_none_on_non_windows(monkeypatch):
    import sys

    monkeypatch.setattr(sys, "platform", "linux")
    src = UIAutomationSource()
    assert src.sample() is None


def test_config_helper_defaults():
    from shadow.config import uia_config

    d = uia_config({})
    assert d["enabled"] is True
    assert d["max_depth"] == 8
    assert d["max_elements"] == 500


def test_config_helper_overrides():
    from shadow.config import uia_config

    cfg = {"perception": {"uia": {"max_depth": 3}}}
    d = uia_config(cfg)
    assert d["max_depth"] == 3
    assert d["max_elements"] == 500  # default preserved


def test_icon_glyph_text_control_excluded():
    src = UIAutomationSource()
    root = FakeControl(
        name="Root",
        control_type="WindowControl",
        children=[
            FakeControl(name="Save", control_type="ButtonControl"),
            FakeControl(name="\ue123", control_type="TextControl"),  # icon
            FakeControl(name="", control_type="TextControl"),  # empty
        ],
    )
    node = src._walk(root, depth=0)
    assert node is not None
    assert len(node.children) == 1
    assert node.children[0].name == "Save"


def test_normal_text_control_still_kept():
    src = UIAutomationSource()
    root = FakeControl(
        name="Root",
        control_type="WindowControl",
        children=[
            FakeControl(name="Hello world", control_type="TextControl"),
        ],
    )
    node = src._walk(root, depth=0)
    assert node is not None
    assert len(node.children) == 1


def test_is_noise_text_helper():
    assert UIAutomationSource._is_noise_text("") is True
    assert UIAutomationSource._is_noise_text("\ue100") is True
    assert UIAutomationSource._is_noise_text("\ue100\ue200") is True
    assert UIAutomationSource._is_noise_text("Save") is False
    assert UIAutomationSource._is_noise_text("\ue100Save") is False
