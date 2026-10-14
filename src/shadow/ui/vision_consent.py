"""First-use vision consent dialog.

A modal shown exactly once per install. PRD Section 30.19 requires
this before the very first vision call. Acceptance is recorded in
schema_meta so the user is not asked again.
"""

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

META_KEY = "vision_consent_accepted"


class VisionConsentDialog(QDialog):
    """Modal dialog explaining vision before the first use."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SHADOW — Enable vision?")
        self.setModal(True)
        self.resize(520, 380)
        self.accepted_choice = False

        layout = QVBoxLayout(self)

        title = QLabel("<h2>Analyze screen with local vision</h2>")
        layout.addWidget(title)

        body = QLabel(
            "SHADOW can analyze the active window with a local vision "
            'model. This is used only when you ask ("describe this", '
            '"what am I looking at") or press Ctrl+Shift+V.\n\n'
            "• The model runs on your device. Nothing is sent to any "
            "server.\n"
            "• No screenshots are stored — only short text captions.\n"
            "• Password managers, banking apps, and private browsing "
            "windows are excluded automatically.\n"
            "• You can turn vision off at any time in Settings → Vision."
        )
        body.setWordWrap(True)
        layout.addWidget(body)

        layout.addStretch()

        row = QHBoxLayout()
        row.addStretch()

        cancel_btn = QPushButton("Not now")
        cancel_btn.clicked.connect(self._on_cancel)
        row.addWidget(cancel_btn)

        accept_btn = QPushButton("I understand")
        accept_btn.setDefault(True)
        accept_btn.clicked.connect(self._on_accept)
        row.addWidget(accept_btn)

        layout.addLayout(row)

    def _on_accept(self):
        self.accepted_choice = True
        self.accept()

    def _on_cancel(self):
        self.accepted_choice = False
        self.reject()


class VisionConsent:
    """Persistent state for the first-use consent flag."""

    def __init__(self, memory):
        self.memory = memory

    def is_accepted(self) -> bool:
        try:
            return self.memory.get_meta(META_KEY) == "1"
        except Exception:
            return False

    def accept(self) -> None:
        try:
            self.memory.set_meta(META_KEY, "1")
        except Exception:
            pass

    def reset(self) -> None:
        try:
            self.memory.set_meta(META_KEY, "0")
        except Exception:
            pass
