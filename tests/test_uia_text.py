from shadow.perception import (
    TextBlock,
    UIANode,
    UIATextExtractor,
)


def node(name="", control_type="TextControl", depth=0, children=None):
    return UIANode(
        name=name,
        control_type=control_type,
        children=children or [],
    )


def test_empty_tree_returns_empty():
    root = node(name="Root", control_type="WindowControl")
    result = UIATextExtractor().extract(root)
    assert result["text"] == ""
    assert result["char_count"] == 0
    assert result["truncated"] is False


def test_simple_paragraph_extracted():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Hello world, this is a paragraph.", "TextControl"),
        ],
    )
    result = UIATextExtractor().extract(root)
    assert "Hello world, this is a paragraph." in result["text"]


def test_button_labels_skipped():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Save", "ButtonControl"),
            node("Cancel", "ButtonControl"),
            node("Real content here", "TextControl"),
        ],
    )
    result = UIATextExtractor().extract(root)
    assert "Save" not in result["text"]
    assert "Cancel" not in result["text"]
    assert "Real content here" in result["text"]


def test_menu_items_skipped():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("File", "MenuItemControl"),
            node("Edit", "MenuItemControl"),
            node("Content", "TextControl"),
        ],
    )
    result = UIATextExtractor().extract(root)
    assert "File" not in result["text"]
    assert "Edit" not in result["text"]
    assert "Content" in result["text"]


def test_headings_preserved():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Introduction", "HeadingControl"),
            node("Body text here.", "TextControl"),
        ],
    )
    result = UIATextExtractor().extract(root)
    assert "Introduction" in result["text"]
    assert "Body text here." in result["text"]


def test_hyperlink_text_kept():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Click here to learn more", "HyperlinkControl"),
        ],
    )
    result = UIATextExtractor().extract(root)
    assert "Click here to learn more" in result["text"]


def test_password_fields_excluded():
    pwd = node("secret", "EditControl")
    pwd.is_password = True
    root = node("Root", "WindowControl", children=[pwd])
    result = UIATextExtractor().extract(root)
    assert "secret" not in result["text"]


def test_offscreen_fields_excluded():
    off = node("hidden content", "TextControl")
    off.is_offscreen = True
    root = node("Root", "WindowControl", children=[off])
    result = UIATextExtractor().extract(root)
    assert "hidden content" not in result["text"]


def test_short_text_ignored():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("a", "TextControl"),  # 1 char, below MIN_BLOCK_CHARS
            node("Real text", "TextControl"),
        ],
    )
    result = UIATextExtractor().extract(root)
    assert "Real text" in result["text"]


def test_whitespace_collapsed():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("  Multiple    spaces\n\nhere  ", "TextControl"),
        ],
    )
    result = UIATextExtractor().extract(root)
    assert "Multiple spaces here" in result["text"]


def test_bullet_prefix_stripped():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("• First item", "ListItemControl"),
            node("- Second item", "ListItemControl"),
        ],
    )
    result = UIATextExtractor().extract(root)
    assert "First item" in result["text"]
    assert "Second item" in result["text"]
    assert "•" not in result["text"]
    assert "- Second" not in result["text"]


def test_adjacent_duplicates_dropped():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Same line", "TextControl"),
            node("Same line", "TextControl"),
            node("Different line", "TextControl"),
        ],
    )
    result = UIATextExtractor().extract(root)
    assert result["text"].count("Same line") == 1
    assert "Different line" in result["text"]


def test_truncation_at_max_chars():
    long_text = "word " * 2000  # 10000 chars
    root = node(
        "Root",
        "WindowControl",
        children=[
            node(long_text, "TextControl"),
        ],
    )
    extractor = UIATextExtractor(max_chars=100)
    result = extractor.extract(root)
    assert result["truncated"] is True
    assert result["char_count"] <= 105  # 100 + ellipsis marker
    assert result["text"].endswith("[…]")


def test_no_truncation_when_short():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("short content", "TextControl"),
        ],
    )
    result = UIATextExtractor(max_chars=100).extract(root)
    assert result["truncated"] is False


def test_blocks_preserve_control_types():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Heading", "HeadingControl"),
            node("Body", "TextControl"),
        ],
    )
    result = UIATextExtractor().extract(root)
    types = [b["control_type"] for b in result["blocks"]]
    assert "HeadingControl" in types
    assert "TextControl" in types


def test_blocks_preserve_depth():
    inner = node("Inner", "TextControl")
    mid = node("Mid", "TextControl", children=[inner])
    root = node("Root", "WindowControl", children=[mid])
    result = UIATextExtractor().extract(root)
    depths = {b["text"]: b["depth"] for b in result["blocks"]}
    assert depths["Mid"] == 1
    assert depths["Inner"] == 2


def test_document_control_extracted():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Document body text", "DocumentControl"),
        ],
    )
    result = UIATextExtractor().extract(root)
    assert "Document body text" in result["text"]


def test_edit_control_extracted():
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Editable content", "EditControl"),
        ],
    )
    result = UIATextExtractor().extract(root)
    assert "Editable content" in result["text"]


def test_nested_structure_extracted():
    inner = node("Nested paragraph content", "TextControl")
    section = node("Section", "HeadingControl", children=[inner])
    root = node("Root", "WindowControl", children=[section])
    result = UIATextExtractor().extract(root)
    assert "Section" in result["text"]
    assert "Nested paragraph content" in result["text"]


def test_text_block_to_dict():
    block = TextBlock(text="hello", control_type="TextControl", depth=2)
    d = block.to_dict()
    assert d["text"] == "hello"
    assert d["control_type"] == "TextControl"
    assert d["depth"] == 2
