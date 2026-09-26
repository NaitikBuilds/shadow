import sys

import pytest

from shadow.perception import ActiveWindowSource, PerceptionSource


def test_source_is_perception_source():
    src = ActiveWindowSource()
    assert isinstance(src, PerceptionSource)


def test_metadata():
    src = ActiveWindowSource()
    assert src.name == "active_window"
    assert src.channel == "screen_capture"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only source")
def test_sample_returns_dict_or_none():
    src = ActiveWindowSource()
    result = src.sample()
    # In a headless runner there may be no foreground window;
    # on a normal desktop there will be. Both are valid.
    if result is not None:
        assert set(result.keys()) == {"title", "process", "pid", "timestamp"}
        assert isinstance(result["title"], str)
        assert isinstance(result["process"], str)
        assert isinstance(result["pid"], int)
        assert isinstance(result["timestamp"], str)
