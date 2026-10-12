"""VisionPopup — small non-blocking prompt for on-demand vision.

A frameless widget anchored to the bottom-right of the primary
monitor. Appears when the observer detects visual content and the
offer policy allows it. Auto-dismisses after 30 s.

Never steals focus: WA_ShowWithoutActivating keeps the user's
workflow uninterrupted.
"""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

AUTO_DISMISS_SEC = 30
MARGIN_PX = 20


class VisionPopup(QFrame):
    """Popup prompt offering vision on the active window."""

    choice_made = Signal(str)  # "yes" | "not_now" | "never"

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setFixedWidth(340)
        self.setObjectName("VisionPopup")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        title = QLabel("<b>SHADOW — this looks visual.</b>")
        layout.addWidget(title)

        self.context_label = QLabel("")
        self.context_label.setObjectName("VisionContext")
        self.context_label.setWordWrap(True)
        layout.addWidget(self.context_label)

        hint = QLabel("Want me to take a look?")
        hint.setStyleSheet("color: #444;")
        layout.addWidget(hint)

        row = QHBoxLayout()
        row.addStretch()

        self.yes_btn = QPushButton("Yes")
        self.yes_btn.clicked.connect(lambda: self._emit_choice("yes"))
        row.addWidget(self.yes_btn)

        self.not_now_btn = QPushButton("Not now")
        self.not_now_btn.clicked.connect(lambda: self._emit_choice("not_now"))
        row.addWidget(self.not_now_btn)

        self.never_btn = QPushButton("Don't ask again")
        self.never_btn.clicked.connect(lambda: self._emit_choice("never"))
        row.addWidget(self.never_btn)

        layout.addLayout(row)

        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._on_dismiss_timeout)

        self._apply_style()

    # ---------- public API ----------

    def show_for(self, payload: dict) -> None:
        """Show with context from the observer. Restarts auto-dismiss."""
        process = payload.get("process", "")
        title = payload.get("title", "")
        context_text = title or process or "(unknown window)"
        self.context_label.setText(context_text[:120])

        self._position_bottom_right()
        self.show()
        self.raise_()
        self._dismiss_timer.start(AUTO_DISMISS_SEC * 1000)

    def dismiss(self) -> None:
        self._dismiss_timer.stop()
        self.hide()

    # ---------- internals ----------

    def _emit_choice(self, choice: str) -> None:
        self.dismiss()
        self.choice_made.emit(choice)

    def _on_dismiss_timeout(self) -> None:
        # Timeout counts as "not now" so the cooldown applies.
        self.dismiss()
        self.choice_made.emit("not_now")

    def _position_bottom_right(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.adjustSize()
        w, h = self.width(), self.height()
        x = geo.right() - w - MARGIN_PX
        y = geo.bottom() - h - MARGIN_PX
        self.move(x, y)

    def _apply_style(self) -> None:
        """Force light theme with explicit text colors.

        Qt inherits the OS palette by default. In Windows dark mode that
        means white text on our light background — unreadable. We force
        every color explicitly so the popup is legible regardless of the
        system theme.
        """
        self.setStyleSheet("""
            QFrame#VisionPopup {
                background-color: #ffffff;
                border: 1px solid #d0d0d0;
                border-radius: 8px;
            }
            QFrame#VisionPopup QLabel {
                color: #222222;
                background-color: transparent;
            }
            QFrame#VisionPopup QLabel#VisionContext {
                color: #666666;
                font-size: 11px;
            }
            QFrame#VisionPopup QPushButton {
                color: #222222;
                background-color: #f5f5f5;
                padding: 4px 10px;
                border: 1px solid #c0c0c0;
                border-radius: 4px;
                min-width: 60px;
                font-weight: 500;
            }
            QFrame#VisionPopup QPushButton:hover {
                color: #000000;
                background-color: #e8e8e8;
            }
            QFrame#VisionPopup QPushButton:pressed {
                background-color: #d8d8d8;
            }
            """)
