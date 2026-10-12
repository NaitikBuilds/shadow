
from shadow.hal import VisionService


class FakeBackend:
    """Stand-in vision backend that records calls."""

    def __init__(self, reply: str = "fake caption"):
        self.reply = reply
        self.calls: list[tuple] = []
        self.closed = False

    def understand_image(self, image_bytes, task="caption", prompt=""):
        self.calls.append((image_bytes[:8], task, prompt))
        return self.reply

    def close(self):
        self.closed = True


def test_disabled_returns_empty():
    factory_calls = {"n": 0}

    def factory():
        factory_calls["n"] += 1
        return FakeBackend()

    service = VisionService(factory, enabled=False)
    assert service.analyze(b"some bytes") == ""
    assert factory_calls["n"] == 0


def test_lazy_load_only_on_first_call():
    factory_calls = {"n": 0}

    def factory():
        factory_calls["n"] += 1
        return FakeBackend("first caption")

    service = VisionService(factory)
    assert factory_calls["n"] == 0

    result = service.analyze(b"img1")
    assert result == "first caption"
    assert factory_calls["n"] == 1

    result = service.analyze(b"img2")
    assert result == "first caption"
    assert factory_calls["n"] == 1  # factory only called once


def test_empty_image_returns_empty():
    service = VisionService(lambda: FakeBackend())
    assert service.analyze(b"") == ""


def test_factory_exception_marks_load_failed():
    def bad_factory():
        raise RuntimeError("cannot load")

    service = VisionService(bad_factory)
    assert service.analyze(b"x") == ""
    assert service.is_available() is False
    # Second call should not retry
    assert service.analyze(b"x") == ""


def test_backend_exception_returns_empty():
    class BrokenBackend:
        def understand_image(self, *a, **kw):
            raise RuntimeError("inference failed")

        def close(self):
            pass

    service = VisionService(lambda: BrokenBackend())
    assert service.analyze(b"x") == ""


def test_is_loaded_false_before_first_call():
    service = VisionService(lambda: FakeBackend())
    assert service.is_loaded() is False
    service.analyze(b"x")
    assert service.is_loaded() is True


def test_is_available_reflects_enabled_and_failure():
    service = VisionService(lambda: FakeBackend(), enabled=True)
    assert service.is_available() is True

    service.set_enabled(False)
    assert service.is_available() is False

    service.set_enabled(True)
    assert service.is_available() is True


def test_close_releases_backend():
    backend = FakeBackend()
    service = VisionService(lambda: backend)
    service.analyze(b"x")
    assert backend.closed is False

    service.close()
    assert backend.closed is True
    assert service.is_loaded() is False


def test_close_is_idempotent():
    backend = FakeBackend()
    service = VisionService(lambda: backend)
    service.close()
    service.close()  # second close should not raise
    assert backend.closed is False  # never loaded, never closed


def test_convenience_caption():
    backend = FakeBackend("a cat")
    service = VisionService(lambda: backend)
    assert service.caption(b"x") == "a cat"
    assert backend.calls[0][1] == "caption"


def test_convenience_detailed_caption():
    backend = FakeBackend("long description")
    service = VisionService(lambda: backend)
    service.detailed_caption(b"x")
    assert backend.calls[0][1] == "detailed_caption"


def test_convenience_ocr():
    backend = FakeBackend("extracted text")
    service = VisionService(lambda: backend)
    service.ocr(b"x")
    assert backend.calls[0][1] == "ocr"


def test_convenience_query_passes_prompt():
    backend = FakeBackend("answer")
    service = VisionService(lambda: backend)
    result = service.query(b"x", "What color is the sky?")
    assert result == "answer"
    assert backend.calls[0][1] == "query"
    assert backend.calls[0][2] == "What color is the sky?"
