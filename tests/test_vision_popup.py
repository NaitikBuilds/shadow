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


def test_popup_constructs(qapp):
    from shadow.ui.vision_popup import VisionPopup

    popup = VisionPopup()
    assert popup is not None


def test_popup_has_three_buttons(qapp):
    from shadow.ui.vision_popup import VisionPopup

    popup = VisionPopup()
    assert popup.yes_btn.text() == "Yes"
    assert popup.not_now_btn.text() == "Not now"
    assert popup.never_btn.text() == "Don't ask again"


def test_yes_emits_choice(qapp):
    from shadow.ui.vision_popup import VisionPopup

    popup = VisionPopup()
    captured = []
    popup.choice_made.connect(captured.append)
    popup.yes_btn.click()
    assert captured == ["yes"]


def test_not_now_emits_choice(qapp):
    from shadow.ui.vision_popup import VisionPopup

    popup = VisionPopup()
    captured = []
    popup.choice_made.connect(captured.append)
    popup.not_now_btn.click()
    assert captured == ["not_now"]


def test_never_emits_choice(qapp):
    from shadow.ui.vision_popup import VisionPopup

    popup = VisionPopup()
    captured = []
    popup.choice_made.connect(captured.append)
    popup.never_btn.click()
    assert captured == ["never"]


def test_show_for_updates_context_label(qapp):
    from shadow.ui.vision_popup import VisionPopup

    popup = VisionPopup()
    popup.show_for(
        {
            "process": "chrome.exe",
            "title": "GitHub — Dashboard",
            "category": "browser",
        }
    )
    assert "GitHub" in popup.context_label.text()


def test_dismiss_hides_popup(qapp):
    from shadow.ui.vision_popup import VisionPopup

    popup = VisionPopup()
    popup.show_for({"process": "x.exe", "title": "Test"})
    popup.dismiss()
    assert popup.isVisible() is False


def test_auto_dismiss_constant():
    from shadow.ui.vision_popup import AUTO_DISMISS_SEC

    assert AUTO_DISMISS_SEC == 30
