from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class ObservationIndicator(QWidget):
    """A calm, always-visible strip showing what SHADOW is observing."""

    def __init__(self, memory, config):
        super().__init__()
        self.memory = memory
        self.config = config

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        self.dot = QLabel("●")
        self.dot.setStyleSheet("font-size: 14px;")
        layout.addWidget(self.dot)

        self.text = QLabel()
        layout.addWidget(self.text)
        layout.addStretch()

        self.refresh()

    def refresh(self):
        enabled = [
            ch for ch, on in self.memory.all_consents().items() if on
        ]
        if not enabled:
            self.dot.setStyleSheet("color: #777; font-size: 14px;")
            self.text.setText("Not observing anything")
        else:
            self.dot.setStyleSheet("color: #2ecc71; font-size: 14px;")
            pretty = ", ".join(ch.replace("_", " ") for ch in enabled)
            self.text.setText(f"Observing: {pretty}")