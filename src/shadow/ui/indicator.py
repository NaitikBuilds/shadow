"""Observation indicator strip.

Shows what SHADOW is currently observing. Extends to a purple vision
state while the vision model is processing — mandatory per PRD
Section 30.19.
"""

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class ObservationIndicator(QWidget):
    """A calm, always-visible strip showing what SHADOW is observing."""

    def __init__(self, memory, config):
        super().__init__()
        self.memory = memory
        self.config = config
        self._vision_active = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        self.dot = QLabel("●")
        self.dot.setStyleSheet("font-size: 14px;")
        layout.addWidget(self.dot)

        self.text = QLabel()
        layout.addWidget(self.text)
        layout.addStretch()

        self.refresh()

    # ---------- public API ----------

    def refresh(self):
        """Update indicator based on consent state and vision activity."""
        if self._vision_active:
            self._render_vision()
            return

        enabled = [ch for ch, on in self.memory.all_consents().items() if on]
        if not enabled:
            self._render_idle()
        else:
            pretty = ", ".join(ch.replace("_", " ") for ch in enabled)
            self._render_observing(f"Observing: {pretty}")

    def set_vision_active(self, active: bool) -> None:
        """Called when vision starts or finishes processing."""
        self._vision_active = bool(active)
        self.refresh()

    # ---------- internals ----------

    def _render_vision(self):
        self.dot.setStyleSheet("color: #9b59b6; font-size: 14px;")
        self.text.setText("Vision: analyzing current window…")

    def _render_idle(self):
        self.dot.setStyleSheet("color: #777; font-size: 14px;")
        self.text.setText("Not observing anything")

    def _render_observing(self, message: str):
        self.dot.setStyleSheet("color: #2ecc71; font-size: 14px;")
        self.text.setText(message)
