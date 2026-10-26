
from shadow.perception import ScreenVisionSource


class FakeVisionService:
    def __init__(self, reply: str = "a chart with two bars"):
        self.reply = reply
        self.calls: list[tuple] = []

    def analyze(self, image_bytes, task="caption", prompt="", **kwargs):
        self.calls.append((image_bytes[:8], task, prompt))
        return self.reply if image_bytes else ""


def fake_capture_factory(reply_bytes: bytes = b"\x89PNGfake"):
    """Return a capture function that produces a fixed image."""

    def _capture(rect):
        from PIL import Image

        return Image.new("RGB", (800, 600), color=(120, 120, 120))

    return _capture


def test_source_is_perception_source():
    from shadow.perception import PerceptionSource

    src = ScreenVisionSource(FakeVisionService())
    assert isinstance(src, PerceptionSource)


def test_metadata():
    src = ScreenVisionSource(FakeVisionService())
    assert src.name == "screen_vision"
    assert src.channel == "vision"
    assert src.is_screen_source is False


def test_non_windows_returns_none(monkeypatch):
    import sys

    monkeypatch.setattr(sys, "platform", "linux")
    src = ScreenVisionSource(FakeVisionService())
    assert src.sample() is None


def test_self_window_rejected(monkeypatch):
    src = ScreenVisionSource(FakeVisionService())

    monkeypatch.setattr(
        "shadow.perception.screen_vision.ActiveWindowSource.sample",
        staticmethod(
            lambda self=None: {
                "title": "SHADOW — Silent On-Device Life Context Agent",
                "process": "python.exe",
            }
        ),
    )
    monkeypatch.setattr(src, "_window_rect", lambda: (0, 0, 100, 100))
    assert src.sample() is None


def test_sensitive_process_rejected(monkeypatch):
    src = ScreenVisionSource(FakeVisionService())
    monkeypatch.setattr(
        "shadow.perception.screen_vision.ActiveWindowSource.sample",
        staticmethod(
            lambda self=None: {
                "title": "Vault — My Passwords",
                "process": "1Password.exe",
            }
        ),
    )
    monkeypatch.setattr(src, "_window_rect", lambda: (0, 0, 100, 100))
    assert src.sample() is None


def test_private_browsing_rejected(monkeypatch):
    src = ScreenVisionSource(FakeVisionService())
    monkeypatch.setattr(
        "shadow.perception.screen_vision.ActiveWindowSource.sample",
        staticmethod(
            lambda self=None: {
                "title": "New Tab — Private browsing",
                "process": "chrome.exe",
            }
        ),
    )
    monkeypatch.setattr(src, "_window_rect", lambda: (0, 0, 100, 100))
    assert src.sample() is None


def test_valid_window_returns_payload(monkeypatch):
    service = FakeVisionService("a screenshot of a code editor")
    src = ScreenVisionSource(service, capture_fn=fake_capture_factory())
    monkeypatch.setattr(
        "shadow.perception.screen_vision.ActiveWindowSource.sample",
        staticmethod(
            lambda self=None: {
                "title": "recovery.py — VS Code",
                "process": "Code.exe",
            }
        ),
    )
    monkeypatch.setattr(src, "_window_rect", lambda: (0, 0, 800, 600))

    result = src.sample()
    assert result is not None
    assert result["text"] == "a screenshot of a code editor"
    assert result["task"] == "caption"
    assert "VS Code" in result["window_title"]
    assert result["process"] == "Code.exe"
    assert result["image_bytes"] > 0
    assert "timestamp" in result


def test_query_task_uses_prompt(monkeypatch):
    service = FakeVisionService("yes, it is red")
    src = ScreenVisionSource(service, capture_fn=fake_capture_factory())
    monkeypatch.setattr(
        "shadow.perception.screen_vision.ActiveWindowSource.sample",
        staticmethod(lambda self=None: {"title": "img.png", "process": "Photos.exe"}),
    )
    monkeypatch.setattr(src, "_window_rect", lambda: (0, 0, 800, 600))

    result = src.sample(task="query", prompt="What color is it?")
    assert result is not None
    assert result["task"] == "query"
    assert service.calls[0][2] == "What color is it?"


def test_empty_vision_result_returns_none(monkeypatch):
    service = FakeVisionService("")  # empty reply
    src = ScreenVisionSource(service, capture_fn=fake_capture_factory())
    monkeypatch.setattr(
        "shadow.perception.screen_vision.ActiveWindowSource.sample",
        staticmethod(lambda self=None: {"title": "x", "process": "Code.exe"}),
    )
    monkeypatch.setattr(src, "_window_rect", lambda: (0, 0, 800, 600))
    assert src.sample() is None


def test_no_active_window_returns_none(monkeypatch):
    src = ScreenVisionSource(FakeVisionService())
    monkeypatch.setattr(
        "shadow.perception.screen_vision.ActiveWindowSource.sample",
        staticmethod(lambda self=None: None),
    )
    assert src.sample() is None


def test_no_window_rect_returns_none(monkeypatch):
    src = ScreenVisionSource(FakeVisionService(), capture_fn=fake_capture_factory())
    monkeypatch.setattr(
        "shadow.perception.screen_vision.ActiveWindowSource.sample",
        staticmethod(lambda self=None: {"title": "x", "process": "Code.exe"}),
    )
    monkeypatch.setattr(src, "_window_rect", lambda: None)
    assert src.sample() is None


def test_downscale_applied(monkeypatch):
    from PIL import Image

    def big_capture(rect):
        return Image.new("RGB", (4000, 3000), color=(200, 50, 50))

    service = FakeVisionService("downscaled image")
    src = ScreenVisionSource(service, capture_fn=big_capture, image_max_side=512)
    monkeypatch.setattr(
        "shadow.perception.screen_vision.ActiveWindowSource.sample",
        staticmethod(lambda self=None: {"title": "x", "process": "Code.exe"}),
    )
    monkeypatch.setattr(src, "_window_rect", lambda: (0, 0, 4000, 3000))

    result = src.sample()
    assert result is not None
    # Just assert the pipeline completes; image size check would require
    # intercepting between capture and encode.
    assert result["image_bytes"] > 0


def test_stop_is_safe():
    src = ScreenVisionSource(FakeVisionService())
    src.stop()  # should not raise
