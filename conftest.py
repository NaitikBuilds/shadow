"""Pytest-wide fixtures for SHADOW."""

import pytest


@pytest.fixture(scope="session", autouse=True)
def _qt_cleanup():
    """Ensure any Qt QApplication is quit at end of session.

    Without this, PySide6 can leave native resources alive and the
    process returns exit code 1 on Windows even when all tests passed.
    """
    yield
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.quit()
            app.processEvents()
    except Exception:
        pass
