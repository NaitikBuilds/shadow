import sys

import pytest

# Qt tests need a QApplication. Skip on headless environments.
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
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"QApplication unavailable: {exc}")
    yield app


def test_make_shadow_icon(qapp):
    from shadow.ui.notifications import make_shadow_icon

    icon = make_shadow_icon(64)
    assert not icon.isNull()


def test_tray_notifier_constructs(qapp):
    from shadow.ui.notifications import TrayNotifier

    notifier = TrayNotifier()
    assert notifier.tray is not None


def test_tray_notifier_has_quit_action(qapp):
    from shadow.ui.notifications import TrayNotifier

    notifier = TrayNotifier()
    menu = notifier.tray.contextMenu()
    assert menu is not None
    labels = [a.text() for a in menu.actions()]
    assert any("Quit" in label for label in labels)
    assert any("Show" in label for label in labels)


def test_notify_accepts_shadow_error(qapp):
    from shadow.errors import Severity, ShadowError
    from shadow.ui.notifications import TrayNotifier

    notifier = TrayNotifier()
    err = ShadowError(
        severity=Severity.TRAY,
        feature="test",
        reason="something happened",
        user_action="retry",
    )
    # Should not raise
    notifier.notify(err)


def test_minimize_hint_shown_once(qapp):
    from shadow.ui.notifications import TrayNotifier

    notifier = TrayNotifier()
    assert notifier._minimize_hint_shown is False
    notifier.show_minimize_hint()
    assert notifier._minimize_hint_shown is True
    notifier.show_minimize_hint()
    assert notifier._minimize_hint_shown is True
