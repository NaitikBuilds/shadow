from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class PrivacyDashboard(QWidget):
    """One screen for consent state, activity log, and local wipe."""

    def __init__(self, memory, backend):
        super().__init__()
        self.memory = memory
        self.backend = backend

        layout = QVBoxLayout(self)

        title = QLabel("<h2>Privacy Dashboard</h2>")
        layout.addWidget(title)

        tabs = QTabWidget()
        tabs.addTab(self._build_consent_tab(), "Consent")
        tabs.addTab(self._build_activity_tab(), "Activity")
        tabs.addTab(self._build_data_tab(), "Data")
        layout.addWidget(tabs)

        self.refresh()

    def _build_consent_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.consent_list = QListWidget()
        layout.addWidget(self.consent_list)
        return w

    def _build_activity_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.activity_list = QListWidget()
        layout.addWidget(self.activity_list)
        return w

    def _build_data_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        info = self.backend.info
        layout.addWidget(QLabel(f"<b>Backend:</b> {info['backend'].upper()}"))
        layout.addWidget(QLabel(f"<b>Model:</b> {info.get('model', 'unknown')}"))
        layout.addWidget(QLabel(f"<b>Embedder:</b> {info.get('embedder', 'none')}"))
        layout.addWidget(QLabel(f"<b>Threads:</b> {info.get('threads', '?')}"))

        row = QHBoxLayout()
        self.wipe_btn = QPushButton("Wipe all local memory")
        self.wipe_btn.clicked.connect(self._wipe)
        row.addWidget(self.wipe_btn)
        row.addStretch()
        layout.addLayout(row)
        layout.addStretch()
        return w

    def refresh(self):
        self.consent_list.clear()
        for ch, on in self.memory.all_consents().items():
            state = "ON" if on else "off"
            self.consent_list.addItem(f"{ch:24s}  {state}")

        self.activity_list.clear()
        for ts, action, details in self.memory.recent_activity(limit=100):
            self.activity_list.addItem(f"[{ts}] {action} — {details}")

    def _wipe(self):
        self.memory.wipe()
        self.memory.log_activity("wipe", "Full Shadow wipe from Privacy Dashboard")
        self.refresh()
