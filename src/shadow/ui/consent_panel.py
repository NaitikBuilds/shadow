from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

CHANNEL_META = {
    "screen_capture": (
        "Screen content",
        "Reads the active window title and visible text to understand what you're working on.",
    ),
    "document_parsing": (
        "Documents",
        "Parses PDFs and text documents you open so SHADOW can reference them later.",
    ),
    "meeting_audio": (
        "Meeting audio",
        "Transcribes meeting audio locally. Nothing is sent to the cloud.",
    ),
    "calendar": (
        "Calendar",
        "Reads your local calendar to understand your schedule and upcoming commitments.",
    ),
    "typing_dynamics": (
        "Typing rhythm",
        "Observes pause patterns and typing speed to estimate focus and cognitive load.",
    ),
    "webcam_posture": (
        "Webcam (posture)",
        "Optional coarse posture signal. Very coarse — no images are stored.",
    ),
}


class ConsentPanel(QWidget):
    """Per-channel opt-in panel. Emits consent_changed(channel, enabled)."""

    consent_changed = Signal(str, bool)

    def __init__(self, memory, config):
        super().__init__()
        self.memory = memory
        self.config = config
        self.checkboxes: dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)

        title = QLabel("<h2>Consent</h2>")
        subtitle = QLabel(
            "SHADOW observes nothing by default. Enable only what you want it to see."
        )
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)

        for channel, (name, description) in CHANNEL_META.items():
            frame = QFrame()
            frame.setFrameShape(QFrame.Shape.StyledPanel)
            frame_layout = QVBoxLayout(frame)

            cb = QCheckBox(name)
            cb.setChecked(self.memory.get_consent(channel))
            cb.stateChanged.connect(
                lambda state, ch=channel: self._on_toggle(ch, state == 2)
            )
            self.checkboxes[channel] = cb

            desc = QLabel(description)
            desc.setWordWrap(True)
            desc.setStyleSheet("color: #888; font-size: 11px;")

            frame_layout.addWidget(cb)
            frame_layout.addWidget(desc)
            inner_layout.addWidget(frame)

        scroll.setWidget(inner)
        layout.addWidget(scroll)

        enable_all = QPushButton("Disable all")
        enable_all.clicked.connect(self._disable_all)
        layout.addWidget(enable_all)

    def _on_toggle(self, channel: str, enabled: bool):
        self.memory.set_consent(channel, enabled, reason="user toggled in panel")
        self.consent_changed.emit(channel, enabled)

    def _disable_all(self):
        for channel, cb in self.checkboxes.items():
            if cb.isChecked():
                cb.setChecked(False)  # triggers _on_toggle