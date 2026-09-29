"""System tray icon and notification dispatch for SHADOW."""

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


def make_shadow_icon(size: int = 64) -> QIcon:
    """Draw a small icon programmatically — dark circle with a blue core."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)

    painter.setBrush(QBrush(QColor("#1a1a1a")))
    margin = size // 10
    painter.drawEllipse(margin, margin, size - 2 * margin, size - 2 * margin)

    painter.setBrush(QBrush(QColor("#4a90e2")))
    inner = size // 3
    offset = (size - inner) // 2
    painter.drawEllipse(offset, offset, inner, inner)

    painter.end()
    return QIcon(pixmap)


class TrayNotifier(QObject):
    """Owns the QSystemTrayIcon and routes notifications.

    The tray icon persists while SHADOW runs, including when the main
    window is hidden. Quitting the app happens through the tray menu
    or Ctrl+C in the terminal.
    """

    show_window_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.tray = QSystemTrayIcon(make_shadow_icon(), parent)
        self.tray.setToolTip("SHADOW — running")
        self._minimize_hint_shown = False
        self._build_menu()
        self.tray.activated.connect(self._on_activated)

    # ---------- menu ----------

    def _build_menu(self) -> None:
        menu = QMenu()
        show_action = menu.addAction("Show SHADOW")
        show_action.triggered.connect(self.show_window_requested.emit)
        menu.addSeparator()
        quit_action = menu.addAction("Quit SHADOW")
        quit_action.triggered.connect(self.quit_requested.emit)
        self.tray.setContextMenu(menu)

    # ---------- activation ----------

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_window_requested.emit()

    # ---------- visibility ----------

    def show(self) -> None:
        self.tray.show()

    def hide(self) -> None:
        self.tray.hide()

    # ---------- notifications ----------

    def notify(self, error) -> None:
        """Show a system tray message for a ShadowError."""
        title = f"SHADOW — {error.feature}"
        body = error.reason
        if error.user_action:
            body = f"{body}  ·  {error.user_action}"
        self.tray.showMessage(
            title,
            body[:240],
            QSystemTrayIcon.MessageIcon.Warning,
            6000,
        )

    def show_minimize_hint(self) -> None:
        """One-time hint after the window is hidden."""
        if self._minimize_hint_shown:
            return
        self._minimize_hint_shown = True
        self.tray.showMessage(
            "SHADOW",
            "Still running in the background. Right-click the tray icon to quit.",
            QSystemTrayIcon.MessageIcon.Information,
            5000,
        )
