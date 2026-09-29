

from shadow.perception import DocumentSource, PerceptionSource


def test_source_is_perception_source(tmp_path):
    src = DocumentSource([str(tmp_path)], [".txt"])
    assert isinstance(src, PerceptionSource)


def test_metadata(tmp_path):
    src = DocumentSource([str(tmp_path)], [".txt"])
    assert src.name == "document"
    assert src.channel == "document_parsing"


def test_first_sample_seeds_and_returns_none(tmp_path):
    (tmp_path / "existing.txt").write_text("hello world " * 10, encoding="utf-8")
    src = DocumentSource([str(tmp_path)], [".txt"])
    # First call seeds the seen map and returns None
    assert src.sample() is None


def test_new_file_after_seed_is_ingested(tmp_path):
    src = DocumentSource([str(tmp_path)], [".txt"])
    src.sample()  # seed

    # Create a new file after seeding
    new_file = tmp_path / "new.txt"
    new_file.write_text("This is a brand new document. " * 5, encoding="utf-8")

    result = src.sample()
    assert result is not None
    assert result["name"] == "new.txt"
    assert "brand new document" in result["text"]


def test_same_file_not_ingested_twice(tmp_path):
    src = DocumentSource([str(tmp_path)], [".txt"])
    src.sample()  # seed

    f = tmp_path / "once.txt"
    f.write_text("some meaningful content here " * 5, encoding="utf-8")
    first = src.sample()
    assert first is not None

    second = src.sample()
    assert second is None


def test_short_files_ignored(tmp_path):
    src = DocumentSource([str(tmp_path)], [".txt"])
    src.sample()

    (tmp_path / "tiny.txt").write_text("hi", encoding="utf-8")
    assert src.sample() is None


def test_extension_filter(tmp_path):
    src = DocumentSource([str(tmp_path)], [".txt"])
    src.sample()

    (tmp_path / "ignored.md").write_text("lots of words " * 20, encoding="utf-8")
    (tmp_path / "ignored.pdf").write_bytes(b"%PDF-1.4 fake")
    assert src.sample() is None


def test_most_recent_wins(tmp_path):
    src = DocumentSource([str(tmp_path)], [".txt"])
    src.sample()

    old = tmp_path / "old.txt"
    old.write_text("old content " * 20, encoding="utf-8")
    new = tmp_path / "new.txt"
    new.write_text("new content " * 20, encoding="utf-8")
    # Force new to look more recent
    import os
    import time

    time.sleep(0.01)
    os.utime(new, None)

    result = src.sample()
    assert result is not None
    assert result["name"] == "new.txt"


def test_empty_folder_returns_none(tmp_path):
    src = DocumentSource([str(tmp_path)], [".txt"])
    src.sample()  # seed
    assert src.sample() is None


def test_nonexistent_folder_is_safe(tmp_path):
    src = DocumentSource([str(tmp_path / "does_not_exist")], [".txt"])
    assert src.sample() is None  # seed
    assert src.sample() is None  # nothing to find
