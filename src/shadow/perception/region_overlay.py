"""Fullscreen region-selection overlay for SHADOW.

The overlay lets the user select a rectangular screen region by dragging
the mouse. It emits the selected rectangle in virtual-desktop coordinates.

This module deliberately does not capture, store, or analyze screenshots.
Those operations belong to the region-capture pipeline.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget


class RegionCaptureOverlay(QWidget):
    """A dimmed, fullscreen overlay for selecting a screen region.

    Signals:
        region_selected: Emits a QRect in virtual-desktop coordinates.
        cancelled: Emitted when selection is cancelled.
    """

    region_selected = Signal(QRect)
    cancelled = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._origin = None
        self._current = None
        self._selecting = False
        self._finishing = False

        self.setWindowTitle("SHADOW — Select Region")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Use the union of all monitor geometries so the overlay can span
        # the entire virtual desktop, including secondary monitors.
        self._desktop_geometry = self._virtual_desktop_geometry()
        self.setGeometry(self._desktop_geometry)

    @staticmethod
    def _virtual_desktop_geometry() -> QRect:
        """Return the bounding rectangle of all connected screens."""
        screens = QGuiApplication.screens()

        if not screens:
            return QRect(0, 0, 1, 1)

        geometry = QRect(screens[0].geometry())
        for screen in screens[1:]:
            geometry = geometry.united(screen.geometry())

        return geometry

    def begin_selection(self) -> None:
        """Display the overlay and start accepting input."""
        self._origin = None
        self._current = None
        self._selecting = False
        self._finishing = False

        self._desktop_geometry = self._virtual_desktop_geometry()
        self.setGeometry(self._desktop_geometry)

        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        """Draw the dimmed desktop and current selection rectangle."""
        del event

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Dim the desktop beneath the overlay.
        painter.fillRect(self.rect(), QColor(0, 0, 0, 110))

        if self._origin is None or self._current is None:
            painter.setPen(QPen(QColor(255, 255, 255, 230), 1))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Drag to select a region  •  Esc to cancel",
            )
            return

        selection = QRect(self._origin, self._current).normalized()

        # Make the selection visible with a light border and a subtle fill.
        painter.fillRect(selection, QColor(80, 170, 255, 45))
        painter.setPen(QPen(QColor(100, 190, 255, 255), 2))
        painter.drawRect(selection)

        # Display the current selection dimensions.
        painter.setPen(QPen(QColor(255, 255, 255, 240), 1))
        label = f"{selection.width()} × {selection.height()}"
        label_rect = QRect(
            selection.left(),
            max(0, selection.top() - 26),
            160,
            22,
        )
        painter.drawText(
            label_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            label,
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or self._finishing:
            event.ignore()
            return

        self._origin = event.position().toPoint()
        self._current = self._origin
        self._selecting = True
        self.update()
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if not self._selecting or self._finishing:
            return

        self._current = event.position().toPoint()
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if (
            event.button() != Qt.MouseButton.LeftButton
            or not self._selecting
            or self._finishing
        ):
            event.ignore()
            return

        self._current = event.position().toPoint()
        self._selecting = False

        selection = QRect(self._origin, self._current).normalized()

        # Ignore accidental clicks and tiny selections.
        if selection.width() < 2 or selection.height() < 2:
            self.cancel_selection()
            event.accept()
            return

        # The overlay uses virtual-desktop geometry, so translate the local
        # selection to desktop coordinates. This matters when a monitor has
        # a negative x/y coordinate.
        selection.translate(self._desktop_geometry.topLeft())

        self._finishing = True
        self.hide()
        self.region_selected.emit(selection)

        event.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_selection()
            event.accept()
            return

        super().keyPressEvent(event)

    def cancel_selection(self) -> None:
        """Hide the overlay and emit cancellation once."""
        if self._finishing:
            return

        self._finishing = True
        self._selecting = False
        self._origin = None
        self._current = None
        self.hide()
        self.cancelled.emit()

    def closeEvent(self, event) -> None:  # noqa: N802
        """Treat closing the overlay as cancellation."""
        if not self._finishing:
            self.cancel_selection()

        event.accept()

    def reset(self) -> None:
        """Reset internal state so the overlay can be reused."""
        self._origin = None
        self._current = None
        self._selecting = False
        self._finishing = False
        self.update()
