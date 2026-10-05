from shadow.perception import (
    IdentifierExtractor,
    UIANode,
)


def node(name="", control_type="TextControl", children=None):
    return UIANode(
        name=name,
        control_type=control_type,
        children=children or [],
    )


# ---------- URLs ----------


def test_url_from_browser_title():
    ex = IdentifierExtractor()
    result = ex.extract(
        process="chrome.exe",
        title="Docs — https://docs.python.org/3/ — Chrome",
    )
    assert "https://docs.python.org/3/" in result.urls
    assert result.primary_url == "https://docs.python.org/3/"


def test_url_from_uia_edit_control():
    ex = IdentifierExtractor()
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("https://github.com/user/repo", "EditControl"),
        ],
    )
    result = ex.extract(
        process="chrome.exe",
        title="GitHub — Chrome",
        root=root,
    )
    assert "https://github.com/user/repo" in result.urls


def test_url_from_uia_text_control():
    ex = IdentifierExtractor()
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("Visit https://example.com for details", "TextControl"),
        ],
    )
    result = ex.extract(
        process="chrome.exe",
        title="Page — Chrome",
        root=root,
    )
    assert "https://example.com" in result.urls


def test_url_dedup():
    ex = IdentifierExtractor()
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("https://example.com", "EditControl"),
            node("https://example.com", "TextControl"),
        ],
    )
    result = ex.extract(
        process="chrome.exe",
        title="https://example.com — Chrome",
        root=root,
    )
    assert result.urls.count("https://example.com") == 1


def test_url_strips_trailing_punctuation():
    ex = IdentifierExtractor()
    result = ex.extract(
        process="chrome.exe",
        title="(see https://example.com/path).",
    )
    assert any("https://example.com/path" in u for u in result.urls)


def test_url_rejects_non_urls():
    ex = IdentifierExtractor()
    result = ex.extract(
        process="chrome.exe",
        title="No URL here, just text",
    )
    assert result.urls == []


def test_url_max_cap():
    ex = IdentifierExtractor()
    title = " — ".join(f"https://example.com/{i}" for i in range(20))
    result = ex.extract(process="chrome.exe", title=title)
    assert len(result.urls) <= IdentifierExtractor.MAX_URLS


def test_url_not_extracted_for_editor():
    ex = IdentifierExtractor()
    result = ex.extract(
        process="Code.exe",
        title="recovery.py — shadow — VS Code",
    )
    assert result.urls == []


def test_url_query_params_preserved():
    ex = IdentifierExtractor()
    result = ex.extract(
        process="chrome.exe",
        title="Search — https://www.google.com/search?q=python — Chrome",
    )
    assert any("q=python" in u for u in result.urls)


# ---------- Paths ----------


def test_path_from_editor_title():
    ex = IdentifierExtractor()
    result = ex.extract(
        process="Code.exe",
        title="recovery.py — shadow — Visual Studio Code",
    )
    assert "recovery.py" in result.paths
    assert result.primary_path == "recovery.py"


def test_path_from_windows_full_path():
    ex = IdentifierExtractor()
    result = ex.extract(
        process="Code.exe",
        title=r"C:\Users\naiti\shadow\recovery.py — VS Code",
    )
    assert any(r"recovery.py" in p for p in result.paths)


def test_path_from_unix_full_path():
    ex = IdentifierExtractor()
    result = ex.extract(
        process="Code.exe",
        title="/home/user/shadow/recovery.py — VS Code",
    )
    assert any("recovery.py" in p for p in result.paths)


def test_path_from_uia_breadcrumb():
    ex = IdentifierExtractor()
    root = node(
        "Root",
        "WindowControl",
        children=[
            node(r"C:\Users\naiti\shadow\agent\recovery.py", "TextControl"),
        ],
    )
    result = ex.extract(
        process="Code.exe",
        title="recovery.py — VS Code",
        root=root,
    )
    assert any("recovery.py" in p for p in result.paths)


def test_path_from_file_uri():
    ex = IdentifierExtractor()
    root = node(
        "Root",
        "WindowControl",
        children=[
            node("file:///home/user/project/main.py", "TextControl"),
        ],
    )
    result = ex.extract(
        process="Code.exe",
        title="main.py — VS Code",
        root=root,
    )
    assert any("main.py" in p for p in result.paths)


def test_path_dedup():
    ex = IdentifierExtractor()
    result = ex.extract(
        process="Code.exe",
        title="recovery.py — recovery.py — VS Code",
    )
    assert result.paths.count("recovery.py") == 1


def test_path_not_extracted_for_browser():
    ex = IdentifierExtractor()
    result = ex.extract(
        process="chrome.exe",
        title="Docs — Chrome",
    )
    assert result.paths == []


def test_path_max_cap():
    ex = IdentifierExtractor()
    titles = " — ".join(f"file{i}.py" for i in range(20))
    result = ex.extract(
        process="Code.exe",
        title=titles,
    )
    assert len(result.paths) <= IdentifierExtractor.MAX_PATHS


def test_path_rejects_no_extension():
    ex = IdentifierExtractor()
    result = ex.extract(
        process="Code.exe",
        title="Just a window title — VS Code",
    )
    # "Just a window title" has no extension
    assert result.paths == []


# ---------- Identifiers dataclass ----------


def test_identifiers_primary_fields():
    from shadow.perception import Identifiers

    ident = Identifiers(
        urls=["https://a.com", "https://b.com"],
        paths=["main.py", "other.py"],
    )
    assert ident.primary_url == "https://a.com"
    assert ident.primary_path == "main.py"


def test_identifiers_empty():
    from shadow.perception import Identifiers

    ident = Identifiers()
    assert ident.is_empty() is True
    assert ident.primary_url is None
    assert ident.primary_path is None


def test_identifiers_to_dict():
    from shadow.perception import Identifiers

    ident = Identifiers(urls=["https://a.com"], paths=["x.py"])
    d = ident.to_dict()
    assert d["urls"] == ["https://a.com"]
    assert d["paths"] == ["x.py"]
    assert d["primary_url"] == "https://a.com"
    assert d["primary_path"] == "x.py"


# ---------- OTHER category fallthrough ----------


def test_other_category_tries_both():
    ex = IdentifierExtractor()
    result = ex.extract(
        process="someapp.exe",
        title="https://example.com — file.py",
    )
    # OTHER apps get best-effort URL and path detection
    # At least one should hit
    assert not result.is_empty() or result.urls or result.paths


# ---------- Config ----------


def test_config_helper_defaults():
    from shadow.config import identifiers_config

    d = identifiers_config({})
    assert d["extract_urls"] is True
    assert d["extract_paths"] is True


def test_config_helper_overrides():
    from shadow.config import identifiers_config

    cfg = {"perception": {"identifiers": {"extract_urls": False}}}
    d = identifiers_config(cfg)
    assert d["extract_urls"] is False
    assert d["extract_paths"] is True
