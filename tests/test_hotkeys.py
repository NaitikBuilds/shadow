import sys
import time

import pytest

try:
    from PySide6.QtWidgets import QApplication
except ImportError:
    pytest.skip("Qt not available", allow_module_level=True)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication(sys.argv[:1])
        except Exception as exc:
            pytest.skip(f"QApplication unavailable: {exc}")
    yield app


def test_hotkeys_construct(qapp):
    from shadow.perception import VisionHotkeys

    hotkeys = VisionHotkeys()
    assert hotkeys is not None


def test_disabled_does_not_start(qapp):
    from shadow.perception import VisionHotkeys

    hotkeys = VisionHotkeys(enabled=False)
    hotkeys.start()  # should not raise
    assert hotkeys._listener is None


def test_stop_is_safe_when_never_started(qapp):
    from shadow.perception import VisionHotkeys

    hotkeys = VisionHotkeys()
    hotkeys.stop()  # should not raise


def test_vision_emits_once(qapp):
    from shadow.perception import VisionHotkeys

    hotkeys = VisionHotkeys()
    captured = []
    hotkeys.vision_requested.connect(lambda: captured.append(1))

    hotkeys._on_vision()
    assert len(captured) == 1


def test_vision_debounce(qapp):
    from shadow.perception import VisionHotkeys
    from shadow.perception.hotkeys import DEBOUNCE_MS

    hotkeys = VisionHotkeys()
    captured = []
    hotkeys.vision_requested.connect(lambda: captured.append(1))

    hotkeys._on_vision()
    hotkeys._on_vision()  # within debounce, should be ignored
    assert len(captured) == 1

    time.sleep((DEBOUNCE_MS + 100) / 1000.0)
    hotkeys._on_vision()
    assert len(captured) == 2


def test_region_emits_once(qapp):
    from shadow.perception import VisionHotkeys

    hotkeys = VisionHotkeys()
    captured = []
    hotkeys.region_capture_requested.connect(lambda: captured.append(1))

    hotkeys._on_region()
    assert len(captured) == 1


def test_region_debounce(qapp):
    from shadow.perception import VisionHotkeys

    hotkeys = VisionHotkeys()
    captured = []
    hotkeys.region_capture_requested.connect(lambda: captured.append(1))

    hotkeys._on_region()
    hotkeys._on_region()  # debounced
    assert len(captured) == 1


def test_debounce_constant():
    from shadow.perception.hotkeys import DEBOUNCE_MS

    assert DEBOUNCE_MS == 500


def test_set_enabled_false_stops_listener(qapp):
    from shadow.perception import VisionHotkeys

    hotkeys = VisionHotkeys(enabled=True)
    hotkeys.set_enabled(False)
    assert hotkeys.enabled is False
    assert hotkeys._listener is None


def test_set_enabled_true_reenables(qapp):
    from shadow.perception import VisionHotkeys

    hotkeys = VisionHotkeys(enabled=False)
    hotkeys.set_enabled(True)
    assert hotkeys.enabled is True
    hotkeys.stop()
