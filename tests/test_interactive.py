from shadow.perception import (
    ElementRole,
    InteractiveElement,
    InteractiveExtractor,
    UIANode,
)


def node(
    name="",
    control_type="TextControl",
    enabled=True,
    password=False,
    offscreen=False,
    children=None,
    aid="",
):
    return UIANode(
        name=name,
        control_type=control_type,
        automation_id=aid,
        is_enabled=enabled,
        is_password=password,
        is_offscreen=offscreen,
        children=children or [],
    )


def test_empty_tree_returns_empty():
    root = node("Root", "WindowControl")
    result = InteractiveExtractor().extract(root)
    assert result["count"] == 0
    assert result["elements"] == []


def test_button_extracted():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Save", "ButtonControl"),
        ],
    )
    result = InteractiveExtractor().extract(root)
    assert result["count"] == 1
    assert result["elements"][0]["label"] == "Save"
    assert result["elements"][0]["role"] == "action"


def test_hyperlink_extracted():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Click here", "HyperlinkControl"),
        ],
    )
    result = InteractiveExtractor().extract(root)
    assert result["count"] == 1
    assert result["elements"][0]["role"] == "link"


def test_edit_extracted_as_input():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Search", "EditControl"),
        ],
    )
    result = InteractiveExtractor().extract(root)
    assert result["count"] == 1
    assert result["elements"][0]["role"] == "input"


def test_tab_extracted_as_navigation():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Settings", "TabItemControl"),
        ],
    )
    result = InteractiveExtractor().extract(root)
    assert result["count"] == 1
    assert result["elements"][0]["role"] == "navigation"


def test_slider_extracted_as_selection():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Volume", "SliderControl"),
        ],
    )
    result = InteractiveExtractor().extract(root)
    assert result["count"] == 1
    assert result["elements"][0]["role"] == "selection"


def test_disabled_button_excluded():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Submit", "ButtonControl", enabled=False),
        ],
    )
    result = InteractiveExtractor().extract(root)
    assert result["count"] == 0


def test_icon_only_button_excluded():
    # Empty label — no useful signal
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("", "ButtonControl"),
            node("   ", "ButtonControl"),
        ],
    )
    result = InteractiveExtractor().extract(root)
    assert result["count"] == 0


def test_password_field_excluded():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Password", "EditControl", password=True),
        ],
    )
    result = InteractiveExtractor().extract(root)
    assert result["count"] == 0


def test_text_control_not_extracted():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Just a paragraph", "TextControl"),
        ],
    )
    result = InteractiveExtractor().extract(root)
    assert result["count"] == 0


def test_by_role_aggregation():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Save", "ButtonControl"),
            node("Cancel", "ButtonControl"),
            node("Name", "EditControl"),
            node("Click", "HyperlinkControl"),
        ],
    )
    result = InteractiveExtractor().extract(root)
    assert result["count"] == 4
    assert result["by_role"]["action"] == 2
    assert result["by_role"]["input"] == 1
    assert result["by_role"]["link"] == 1


def test_max_elements_cap():
    children = [node(f"Button {i}", "ButtonControl") for i in range(20)]
    root = node("Root", "WindowControl", children=children)
    result = InteractiveExtractor(max_elements=5).extract(root)
    assert result["count"] == 5


def test_nested_elements_extracted():
    inner = node("Nested Save", "ButtonControl")
    mid = node("Panel", "PaneControl", children=[inner])
    root = node("Root", "WindowControl", children=[mid])
    result = InteractiveExtractor().extract(root)
    assert result["count"] == 1
    assert result["elements"][0]["label"] == "Nested Save"


def test_automation_id_preserved():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Save", "ButtonControl", aid="saveBtn"),
        ],
    )
    result = InteractiveExtractor().extract(root)
    assert result["elements"][0]["automation_id"] == "saveBtn"


def test_bounding_rect_preserved():
    n = node("Save", "ButtonControl")
    n.bounding_rect = (10, 20, 100, 50)
    root = node("Root", "WindowControl", children=[n])
    result = InteractiveExtractor().extract(root)
    assert result["elements"][0]["bounding_rect"] == [10, 20, 100, 50]


def test_long_label_truncated():
    long_label = "A" * 500
    root = node(
        "Root",
        "WindowControl",
        children=[
            node(long_label, "ButtonControl"),
        ],
    )
    result = InteractiveExtractor().extract(root)
    assert len(result["elements"][0]["label"]) <= 120


def test_element_to_dict_serializable():
    el = InteractiveElement(
        label="Save",
        role=ElementRole.ACTION,
        control_type="ButtonControl",
        automation_id="saveBtn",
        is_enabled=True,
        bounding_rect=(10, 20, 100, 50),
        depth=3,
    )
    d = el.to_dict()
    assert d["label"] == "Save"
    assert d["role"] == "action"
    assert d["depth"] == 3
    assert isinstance(d["bounding_rect"], list)


def test_role_map_completeness():
    # Verify every expected control type has a role
    from shadow.perception.interactive import _ROLE_MAP

    assert "ButtonControl" in _ROLE_MAP
    assert "EditControl" in _ROLE_MAP
    assert "HyperlinkControl" in _ROLE_MAP
    assert "TabItemControl" in _ROLE_MAP
    assert "SliderControl" in _ROLE_MAP


def test_config_helper_defaults():
    from shadow.config import interactive_config

    d = interactive_config({})
    assert d["max_elements"] == 100


def test_config_helper_overrides():
    from shadow.config import interactive_config

    cfg = {"perception": {"interactive": {"max_elements": 50}}}
    d = interactive_config(cfg)
    assert d["max_elements"] == 50
