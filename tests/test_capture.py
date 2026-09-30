import pytest

from shadow.agent import QuickCapture
from shadow.memory import MemoryStore


class FakeWindowSource:
    def sample(self):
        return {
            "title": "recovery.py — shadow — Visual Studio Code",
            "process": "Code.exe",
            "pid": 12345,
            "timestamp": "2026-10-01 12:00:00",
        }


class FakeOCRSource:
    def __init__(self, text: str = "Sample captured text from the screen."):
        self.text = text

    def sample(self):
        return {
            "text": self.text,
            "word_count": len(self.text.split()),
            "timestamp": "2026-10-01 12:00:00",
        }


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "capture.db"))
    yield s
    s.close()


@pytest.fixture
def capture(store, tmp_path):
    cfg = {
        "capture": {
            "enabled": True,
            "hotkey": "<ctrl>+<shift>+s",
            "output_dir": str(tmp_path / "captures"),
        }
    }
    return QuickCapture(store, cfg)


def test_disabled_by_default_when_flag_false(store, tmp_path):
    cfg = {"capture": {"enabled": False, "output_dir": str(tmp_path / "c")}}
    cap = QuickCapture(store, cfg)
    cap.start()  # should not raise
    assert cap._listener is None


def test_output_dir_created(capture):
    capture.output_dir.mkdir(parents=True, exist_ok=True)
    assert capture.output_dir.exists()


def test_capture_writes_markdown(capture, monkeypatch):
    monkeypatch.setattr(capture, "_read_active_window", FakeWindowSource().sample)
    monkeypatch.setattr(capture, "_read_ocr_text", lambda: "Captured screen text here.")

    path = capture.capture_once()
    assert path is not None
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "# Quick Capture" in content
    assert "Captured screen text here." in content
    assert "Visual Studio Code" in content


def test_capture_records_observation(capture, monkeypatch):
    monkeypatch.setattr(capture, "_read_active_window", FakeWindowSource().sample)
    monkeypatch.setattr(capture, "_read_ocr_text", lambda: "Some text")

    path = capture.capture_once()
    assert path is not None

    cur = capture.memory.conn.cursor()
    cur.execute("SELECT COUNT(*) FROM observations WHERE source = 'capture'")
    assert cur.fetchone()[0] == 1


def test_capture_returns_none_when_nothing_available(capture, monkeypatch):
    monkeypatch.setattr(capture, "_read_active_window", lambda: None)
    monkeypatch.setattr(capture, "_read_ocr_text", lambda: "")
    assert capture.capture_once() is None


def test_capture_filename_format(capture, monkeypatch):
    monkeypatch.setattr(capture, "_read_active_window", FakeWindowSource().sample)
    monkeypatch.setattr(capture, "_read_ocr_text", lambda: "x")

    path = capture.capture_once()
    assert path is not None
    assert path.suffix == ".md"
    # Format: YYYY-MM-DD_HH-MM-SS.md
    assert len(path.stem) == 19
    assert path.stem[4] == "-"
    assert path.stem[10] == "_"


def test_on_capture_callback_fires(capture, monkeypatch):
    calls = []
    capture.on_capture = calls.append

    monkeypatch.setattr(capture, "_read_active_window", FakeWindowSource().sample)
    monkeypatch.setattr(capture, "_read_ocr_text", lambda: "x")

    capture._on_hotkey()
    assert len(calls) == 1
    assert calls[0].endswith(".md")


def test_markdown_without_ocr_text(capture, monkeypatch):
    monkeypatch.setattr(capture, "_read_active_window", FakeWindowSource().sample)
    monkeypatch.setattr(capture, "_read_ocr_text", lambda: "")

    path = capture.capture_once()
    assert path is not None
    content = path.read_text(encoding="utf-8")
    assert "_No visible text was captured._" in content


def test_stop_is_safe_when_never_started(capture):
    capture.stop()  # should not raise


def test_config_helper_returns_defaults():
    from shadow.config import capture_config

    d = capture_config({})
    assert d["enabled"] is True
    assert d["hotkey"] == "<ctrl>+<shift>+s"
    assert "captures" in d["output_dir"]
