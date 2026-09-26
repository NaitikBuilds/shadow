import sys

import pytest

from shadow.perception import PerceptionSource, ScreenOCRSource


def test_source_is_perception_source():
    assert isinstance(ScreenOCRSource(), PerceptionSource)


def test_metadata():
    src = ScreenOCRSource()
    assert src.name == "screen_ocr"
    assert src.channel == "screen_capture"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only source")
def test_sample_returns_dict_or_none():
    src = ScreenOCRSource()
    result = src.sample()
    # OCR may fail in headless CI, on locked sessions, or on screens with
    # no text. None is a valid answer.
    if result is not None:
        assert set(result.keys()) == {"text", "word_count", "timestamp"}
        assert isinstance(result["text"], str)
        assert isinstance(result["word_count"], int)
        assert len(result["text"]) > 0
        assert result["word_count"] > 0
