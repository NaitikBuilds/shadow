
from shadow.perception import ScreenVisionSource


class FakeVisionService:
    def __init__(self):
        self.calls = 0

    def analyze(self, image_bytes, task="caption", prompt="", **kwargs):
        self.calls += 1
        return "a caption"


class FakeExclusions:
    def __init__(self, excluded: set[str]):
        self.excluded = {e.lower().replace(".exe", "") for e in excluded}

    def is_excluded(self, process: str) -> bool:
        return process.lower().replace(".exe", "") in self.excluded


def fake_capture(rect):
    from PIL import Image

    return Image.new("RGB", (400, 300), color=(100, 100, 100))


def test_excluded_app_not_sampled(monkeypatch):
    service = FakeVisionService()
    exclusions = FakeExclusions({"code.exe"})
    src = ScreenVisionSource(service, capture_fn=fake_capture, exclusions=exclusions)
    monkeypatch.setattr(
        "shadow.perception.screen_vision.ActiveWindowSource.sample",
        staticmethod(
            lambda self=None: {
                "title": "recovery.py — VS Code",
                "process": "Code.exe",
            }
        ),
    )
    monkeypatch.setattr(src, "_window_rect", lambda: (0, 0, 400, 300))
    assert src.sample() is None
    assert service.calls == 0


def test_non_excluded_app_still_sampled(monkeypatch):
    service = FakeVisionService()
    exclusions = FakeExclusions({"code.exe"})
    src = ScreenVisionSource(service, capture_fn=fake_capture, exclusions=exclusions)
    monkeypatch.setattr(
        "shadow.perception.screen_vision.ActiveWindowSource.sample",
        staticmethod(
            lambda self=None: {
                "title": "GitHub — Chrome",
                "process": "chrome.exe",
            }
        ),
    )
    monkeypatch.setattr(src, "_window_rect", lambda: (0, 0, 400, 300))
    result = src.sample()
    assert result is not None
    assert service.calls == 1
