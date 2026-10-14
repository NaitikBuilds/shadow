import sys

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


@pytest.fixture
def memory(tmp_path):
    from shadow.memory import MemoryStore

    s = MemoryStore(str(tmp_path / "consent.db"))
    yield s
    s.close()


def test_consent_starts_unaccepted(memory):
    from shadow.ui.vision_consent import VisionConsent

    vc = VisionConsent(memory)
    assert vc.is_accepted() is False


def test_consent_accept_persists(memory):
    from shadow.ui.vision_consent import VisionConsent

    vc = VisionConsent(memory)
    vc.accept()
    assert vc.is_accepted() is True

    vc2 = VisionConsent(memory)
    assert vc2.is_accepted() is True


def test_consent_reset(memory):
    from shadow.ui.vision_consent import VisionConsent

    vc = VisionConsent(memory)
    vc.accept()
    vc.reset()
    assert vc.is_accepted() is False


def test_dialog_constructs(qapp):
    from shadow.ui.vision_consent import VisionConsentDialog

    dlg = VisionConsentDialog()
    assert dlg is not None
    assert dlg.accepted_choice is False


def test_dialog_accept_choice(qapp):
    from shadow.ui.vision_consent import VisionConsentDialog

    dlg = VisionConsentDialog()
    dlg._on_accept()
    assert dlg.accepted_choice is True


def test_dialog_cancel_choice(qapp):
    from shadow.ui.vision_consent import VisionConsentDialog

    dlg = VisionConsentDialog()
    dlg._on_cancel()
    assert dlg.accepted_choice is False


def test_indicator_has_vision_state(qapp, memory):
    from shadow.ui.indicator import ObservationIndicator

    indicator = ObservationIndicator(memory, {})
    indicator.set_vision_active(True)
    assert "Vision" in indicator.text.text()
    assert "#9b59b6" in indicator.dot.styleSheet()


def test_indicator_reverts_after_vision(qapp, memory):
    from shadow.ui.indicator import ObservationIndicator

    indicator = ObservationIndicator(memory, {})
    indicator.set_vision_active(True)
    indicator.set_vision_active(False)
    assert "Vision" not in indicator.text.text()
