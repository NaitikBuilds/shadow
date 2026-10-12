"""Pytest session-wide cleanup for SHADOW.

On Windows CI runners, PySide6 and Pillow can leave resources alive
that cause the interpreter to exit with code 1 even after all tests
pass. Explicitly quitting Qt and forcing garbage collection at end
of session helps the interpreter exit cleanly.
"""

import gc

import pytest


@pytest.fixture(scope="session", autouse=True)
def _final_cleanup():
    """Quit Qt and force GC at end of session."""
    yield
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.quit()
    except Exception:
        pass
    try:
        gc.collect()
    except Exception:
        pass
