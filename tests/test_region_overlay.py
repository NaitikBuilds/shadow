"""Tests for SHADOW's region-selection overlay."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from shadow.perception.region_overlay import RegionCaptureOverlay


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    yield instance


@pytest.fixture
def overlay(app):
    widget = RegionCaptureOverlay()
    widget.setGeometry(0, 0, 800, 600)
    widget.show()
    app.processEvents()

    yield widget

    widget.hide()
    widget.close()
    app.processEvents()


def make_release_event(point: QPoint) -> QMouseEvent:
    """Build a left-mouse-button release event for deterministic testing."""
    return QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        point,
        point,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )


def test_overlay_initial_state(overlay):
    assert not overlay._selecting
    assert overlay._origin is None
    assert overlay._current is None


def test_cancel_selection_emits_signal(overlay, app):
    cancelled = []
    overlay.cancelled.connect(lambda: cancelled.append(True))

    overlay.cancel_selection()
    app.processEvents()

    assert cancelled == [True]
    assert not overlay.isVisible()


def test_selection_emits_normalized_rectangle(overlay, app):
    selected = []
    overlay.region_selected.connect(selected.append)

    overlay._desktop_geometry = overlay.geometry()
    overlay._origin = QPoint(200, 180)
    overlay._current = QPoint(50, 40)
    overlay._selecting = True

    overlay.mouseReleaseEvent(make_release_event(QPoint(50, 40)))
    app.processEvents()

    assert len(selected) == 1

    rect = selected[0]
    assert rect.width() > 0
    assert rect.height() > 0
    assert rect.left() <= rect.right()
    assert rect.top() <= rect.bottom()
    assert not overlay.isVisible()


def test_tiny_selection_is_cancelled(overlay, app):
    cancelled = []
    overlay.cancelled.connect(lambda: cancelled.append(True))

    overlay._desktop_geometry = overlay.geometry()
    overlay._origin = QPoint(10, 10)
    overlay._current = QPoint(10, 10)
    overlay._selecting = True

    overlay.mouseReleaseEvent(make_release_event(QPoint(10, 10)))
    app.processEvents()

    assert cancelled == [True]
    assert not overlay.isVisible()
