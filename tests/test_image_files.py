
import pytest

from shadow.perception import ImageFileSource, PerceptionSource


class FakeVisionService:
    def __init__(self, caption: str = "a colorful test image", available: bool = True):
        self.caption_text = caption
        self._available = available
        self.calls = 0

    def is_available(self) -> bool:
        return self._available

    def caption(self, image_bytes: bytes) -> str:
        self.calls += 1
        return self.caption_text if image_bytes else ""


@pytest.fixture
def png_bytes():
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color=(200, 50, 50)).save(buf, format="PNG")
    return buf.getvalue()


def test_source_is_perception_source(tmp_path):
    src = ImageFileSource(FakeVisionService(), [str(tmp_path)], [".png"])
    assert isinstance(src, PerceptionSource)


def test_metadata(tmp_path):
    src = ImageFileSource(FakeVisionService(), [str(tmp_path)], [".png"])
    assert src.name == "image_file"
    assert src.channel == "document_parsing"


def test_no_vision_service_returns_none(tmp_path):
    src = ImageFileSource(None, [str(tmp_path)], [".png"])
    assert src.sample() is None


def test_unavailable_vision_service_returns_none(tmp_path):
    src = ImageFileSource(FakeVisionService(available=False), [str(tmp_path)], [".png"])
    assert src.sample() is None


def test_first_sample_seeds(tmp_path, png_bytes):
    (tmp_path / "existing.png").write_bytes(png_bytes)
    src = ImageFileSource(FakeVisionService(), [str(tmp_path)], [".png"])
    # First call seeds, returns None
    assert src.sample() is None


def test_new_file_after_seed_ingested(tmp_path, png_bytes):
    src = ImageFileSource(FakeVisionService("a red square"), [str(tmp_path)], [".png"])
    src.sample()  # seed

    (tmp_path / "fresh.png").write_bytes(png_bytes)
    result = src.sample()
    assert result is not None
    assert result["name"] == "fresh.png"
    assert result["caption"] == "a red square"
    assert result["extension"] == ".png"


def test_same_file_not_ingested_twice(tmp_path, png_bytes):
    src = ImageFileSource(FakeVisionService(), [str(tmp_path)], [".png"])
    src.sample()

    (tmp_path / "once.png").write_bytes(png_bytes)
    first = src.sample()
    assert first is not None

    second = src.sample()
    assert second is None


def test_extension_filter(tmp_path, png_bytes):
    src = ImageFileSource(FakeVisionService(), [str(tmp_path)], [".png"])
    src.sample()

    # jpg should be ignored
    (tmp_path / "ignored.jpg").write_bytes(png_bytes)
    assert src.sample() is None


def test_oversized_file_skipped(tmp_path, png_bytes, monkeypatch):
    src = ImageFileSource(
        FakeVisionService(), [str(tmp_path)], [".png"], max_file_size_mb=0
    )
    src.sample()
    (tmp_path / "big.png").write_bytes(png_bytes)
    assert src.sample() is None


def test_most_recent_wins(tmp_path, png_bytes):
    import os
    import time

    src = ImageFileSource(FakeVisionService(), [str(tmp_path)], [".png"])
    src.sample()

    old = tmp_path / "old.png"
    old.write_bytes(png_bytes)
    time.sleep(0.01)
    new = tmp_path / "new.png"
    new.write_bytes(png_bytes)
    os.utime(new, None)

    result = src.sample()
    assert result is not None
    assert result["name"] == "new.png"


def test_nonexistent_folder_safe():
    src = ImageFileSource(FakeVisionService(), ["/path/that/does/not/exist"], [".png"])
    assert src.sample() is None  # seed
    assert src.sample() is None  # nothing to find


def test_empty_caption_returns_none(tmp_path, png_bytes):
    service = FakeVisionService(caption="")
    src = ImageFileSource(service, [str(tmp_path)], [".png"])
    src.sample()
    (tmp_path / "x.png").write_bytes(png_bytes)
    assert src.sample() is None


def test_downscale_returns_png(tmp_path):
    import io

    from PIL import Image

    src = ImageFileSource(
        FakeVisionService(), [str(tmp_path)], [".png"], image_max_side=32
    )

    buf = io.BytesIO()
    Image.new("RGB", (400, 400), color=(50, 100, 150)).save(buf, format="PNG")
    raw = buf.getvalue()

    out = src._downscale_and_encode(raw)
    assert out.startswith(b"\x89PNG")


def test_config_helper_defaults():
    from shadow.config import image_files_config

    d = image_files_config({})
    assert ".png" in d["extensions"]
    assert ".jpg" in d["extensions"]
    assert d["max_file_size_mb"] == 15


def test_config_helper_overrides():
    from shadow.config import image_files_config

    cfg = {"perception": {"image_files": {"max_file_size_mb": 5}}}
    d = image_files_config(cfg)
    assert d["max_file_size_mb"] == 5
    assert d["image_max_side"] == 1024  # default
