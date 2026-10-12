import json
from datetime import datetime, timedelta

import pytest

from shadow.memory import ImageObservationStore, MemoryStore


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "images.db"))
    yield s
    s.close()


def add_image_file(store, name: str, caption: str, minutes_ago: float = 1.0):
    payload = {
        "path": f"C:/pics/{name}",
        "name": name,
        "extension": "." + name.rsplit(".", 1)[-1],
        "size_bytes": 12345,
        "caption": caption,
    }
    content = f"Image: {name}\n{caption}"
    ts = (datetime.utcnow() - timedelta(minutes=minutes_ago)).isoformat(
        sep=" ", timespec="seconds"
    )
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO observations (timestamp, source, content, metadata) "
        "VALUES (?, 'image_file', ?, ?)",
        (ts, content, json.dumps(payload)),
    )
    store.conn.commit()
    return cur.lastrowid


def add_screen_vision(store, caption: str, minutes_ago: float = 1.0):
    payload = {"text": caption, "task": "caption", "window_title": "x"}
    ts = (datetime.utcnow() - timedelta(minutes=minutes_ago)).isoformat(
        sep=" ", timespec="seconds"
    )
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO observations (timestamp, source, content, metadata) "
        "VALUES (?, 'screen_vision', ?, ?)",
        (ts, caption, json.dumps(payload)),
    )
    store.conn.commit()
    return cur.lastrowid


# ---------- constants ----------


def test_image_sources_constant():
    from shadow.memory import IMAGE_SOURCES

    assert "image_file" in IMAGE_SOURCES
    assert "screen_vision" in IMAGE_SOURCES
    assert "region_capture" in IMAGE_SOURCES


# ---------- queries ----------


def test_empty_store_returns_nothing(store):
    s = ImageObservationStore(store)
    assert s.recent() == []
    assert s.count() == 0


def test_recent_returns_newest_first(store):
    add_image_file(store, "cat.png", "a tabby cat", minutes_ago=10)
    add_image_file(store, "dog.jpg", "a golden retriever", minutes_ago=1)
    recent = ImageObservationStore(store).recent()
    assert len(recent) == 2
    assert recent[0].name == "dog.jpg"
    assert recent[0].caption == "a golden retriever"


def test_recent_includes_screen_vision(store):
    add_image_file(store, "x.png", "an image")
    add_screen_vision(store, "a code editor window")
    recent = ImageObservationStore(store).recent()
    sources = {r.source for r in recent}
    assert sources == {"image_file", "screen_vision"}


def test_count_includes_all_vision_sources(store):
    add_image_file(store, "a.png", "first")
    add_image_file(store, "b.png", "second")
    add_screen_vision(store, "third")
    assert ImageObservationStore(store).count() == 3


def test_between_filters_by_time(store):
    add_image_file(store, "old.png", "old", minutes_ago=120)
    add_image_file(store, "new.png", "new", minutes_ago=5)
    now = datetime.utcnow()
    start = (now - timedelta(minutes=30)).isoformat(sep=" ", timespec="seconds")
    end = now.isoformat(sep=" ", timespec="seconds")
    results = ImageObservationStore(store).between(start, end)
    assert len(results) == 1
    assert results[0].name == "new.png"


def test_by_extension_filters(store):
    add_image_file(store, "a.png", "png image")
    add_image_file(store, "b.jpg", "jpg image")
    add_image_file(store, "c.png", "another png")
    pngs = ImageObservationStore(store).by_extension(".png")
    assert len(pngs) == 2
    assert all(img.extension == ".png" for img in pngs)


def test_by_extension_accepts_bare_extension(store):
    add_image_file(store, "a.png", "png image")
    assert len(ImageObservationStore(store).by_extension("png")) == 1


def test_search_captions_finds_keyword(store):
    add_image_file(store, "a.png", "a red sports car")
    add_image_file(store, "b.png", "a blue bicycle")
    add_image_file(store, "c.png", "another red car")
    results = ImageObservationStore(store).search_captions("red")
    assert len(results) == 2


def test_search_captions_empty_keyword_returns_nothing(store):
    add_image_file(store, "a.png", "anything")
    assert ImageObservationStore(store).search_captions("") == []


# ---------- fallback parsing ----------


def test_caption_falls_back_to_content_parsing(store):
    ts = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO observations (timestamp, source, content) "
        "VALUES (?, 'image_file', ?)",
        (ts, "Image: fallback.png\ncaption from content"),
    )
    store.conn.commit()
    recent = ImageObservationStore(store).recent()
    assert recent[0].name == "fallback.png"
    assert recent[0].caption == "caption from content"


def test_malformed_metadata_does_not_crash(store):
    ts = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO observations (timestamp, source, content, metadata) "
        "VALUES (?, 'image_file', ?, ?)",
        (ts, "Image: bad.png\ncaption", "not json"),
    )
    store.conn.commit()
    recent = ImageObservationStore(store).recent()
    assert recent[0].name == "bad.png"


# ---------- writes ----------


def test_record_screen_vision_persists(store):
    s = ImageObservationStore(store)
    obs_id = s.record_screen_vision(
        text="a screenshot of a code editor",
        window_title="recovery.py — VS Code",
        process="Code.exe",
        task="caption",
    )
    assert obs_id is not None
    recent = s.recent()
    assert len(recent) == 1
    assert recent[0].source == "screen_vision"
    assert recent[0].caption == "a screenshot of a code editor"


def test_record_screen_vision_empty_text_returns_none(store):
    s = ImageObservationStore(store)
    assert s.record_screen_vision(text="") is None
    assert s.record_screen_vision(text="   ") is None


def test_record_screen_vision_count_increments(store):
    s = ImageObservationStore(store)
    before = s.count()
    s.record_screen_vision(text="first", window_title="x", process="y")
    s.record_screen_vision(text="second", window_title="x", process="y")
    assert s.count() == before + 2


# ---------- serialization ----------


def test_to_dict_serializable(store):
    add_image_file(store, "x.png", "an image")
    d = ImageObservationStore(store).recent()[0].to_dict()
    assert d["name"] == "x.png"
    assert d["caption"] == "an image"
    assert d["source"] == "image_file"
    assert isinstance(d["size_bytes"], int)
