from datetime import datetime, timedelta

import pytest

from shadow.agent import ClipboardActionsEngine
from shadow.memory import MemoryStore


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "clip.db"))
    yield s
    s.close()


def add_clip(store, content: str, minutes_ago: float = 1.0):
    ts = (datetime.utcnow() - timedelta(minutes=minutes_ago)).isoformat(
        sep=" ", timespec="seconds"
    )
    prefix = f"Clipboard ({len(content)} chars):\n"
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO observations (timestamp, source, content) "
        "VALUES (?, 'clipboard', ?)",
        (ts, prefix + content),
    )
    store.conn.commit()
    return cur.lastrowid


def test_empty_store_returns_nothing(store):
    assert ClipboardActionsEngine(store).suggest() == []


def test_url_recognized(store):
    add_clip(store, "https://docs.python.org/3/library/pathlib.html")
    insights = ClipboardActionsEngine(store).suggest()
    assert len(insights) == 1
    assert insights[0].kind == "clipboard_url"
    assert "reading list" in insights[0].action.lower()


def test_url_with_newline_not_recognized(store):
    add_clip(store, "https://example.com\nsome extra text\nmore text here")
    insights = ClipboardActionsEngine(store).suggest()
    # Falls through to text classification
    assert insights[0].kind != "clipboard_url"


def test_error_traceback_recognized(store):
    text = (
        "Traceback (most recent call last):\n"
        '  File "test.py", line 10, in <module>\n'
        "ValueError: bad input"
    )
    add_clip(store, text)
    insights = ClipboardActionsEngine(store).suggest()
    assert insights[0].kind == "clipboard_error"
    assert "search" in insights[0].action.lower()


def test_error_word_recognized(store):
    add_clip(store, "Error: connection refused by remote host at 10.0.0.1")
    insights = ClipboardActionsEngine(store).suggest()
    assert insights[0].kind == "clipboard_error"


def test_code_recognized(store):
    code = (
        "def process(x):\n"
        "    result = x * 2\n"
        "    return result\n"
        "\n"
        "print(process(21))"
    )
    add_clip(store, code)
    insights = ClipboardActionsEngine(store).suggest()
    assert insights[0].kind == "clipboard_code"


def test_javascript_code_recognized(store):
    code = "const foo = (x) => {\n  return x + 1;\n};"
    add_clip(store, code)
    insights = ClipboardActionsEngine(store).suggest()
    assert insights[0].kind == "clipboard_code"


def test_plain_text_recognized(store):
    add_clip(store, "This is just a normal paragraph of text that someone copied.")
    insights = ClipboardActionsEngine(store).suggest()
    assert insights[0].kind == "clipboard_text"
    assert "note" in insights[0].action.lower()


def test_short_text_ignored(store):
    add_clip(store, "short")
    insights = ClipboardActionsEngine(store).suggest()
    assert insights == []


def test_old_clipboard_still_visible_but_scored_lower(store):
    add_clip(
        store, "A long piece of text that should still be classified.", minutes_ago=15
    )
    insights = ClipboardActionsEngine(store).suggest()
    assert len(insights) == 1
    assert insights[0].score < 0.4


def test_very_old_clipboard_ignored(store):
    add_clip(store, "A long piece of text that should be ignored.", minutes_ago=60)
    insights = ClipboardActionsEngine(store).suggest()
    assert insights == []


def test_prefix_stripped(store):
    add_clip(store, "https://example.com/xyz")
    insights = ClipboardActionsEngine(store).suggest()
    assert "Clipboard (" not in insights[0].body


def test_dedupes_by_kind(store):
    add_clip(store, "https://one.example.com/a")
    add_clip(store, "https://two.example.com/b")
    add_clip(store, "https://three.example.com/c")
    insights = ClipboardActionsEngine(store).suggest()
    url_kinds = [i for i in insights if i.kind == "clipboard_url"]
    assert len(url_kinds) == 1


def test_respects_limit(store):
    add_clip(store, "https://example.com/unique/path/segment/here")
    add_clip(store, "Error: something went wrong on the server today")
    add_clip(store, "def foo():\n    return 42\n\nprint(foo())")
    add_clip(store, "A plain paragraph of text long enough to be classified.")
    insights = ClipboardActionsEngine(store).suggest(limit=2)
    assert len(insights) == 2
