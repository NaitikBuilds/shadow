"""Cloud settings panel — manage providers, keys, and toggles.

The user can paste API keys without editing config.yaml. Keys are
stored in Windows Credential Manager via keyring, not in YAML or the
database. Connection tests run on a background thread so the UI
doesn't freeze during network calls.
"""

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from shadow.config import (
    cloud_config,
    delete_cloud_key,
    resolve_key,
    set_cloud_key,
)

STATUS_COLORS = {
    "ready": "#2ecc71",
    "cooldown": "#f39c12",
    "no_key": "#888888",
    "error": "#e74c3c",
    "unknown": "#888888",
}


class ConnectionTestWorker(QThread):
    """Runs a provider connection test off the UI thread."""

    finished = Signal(bool, str)

    def __init__(self, provider_name: str, base_url: str, model: str, api_key: str):
        super().__init__()
        self.provider_name = provider_name
        self.base_url = base_url
        self.model = model
        self.api_key = api_key

    def run(self):
        try:
            from shadow.hal.cloud_backend import (
                CloudBackend,
                ProviderConfig,
            )

            cfg = ProviderConfig(
                name=self.provider_name,
                base_url=self.base_url,
                model=self.model,
                api_key=self.api_key,
            )
            backend = CloudBackend(cfg, timeout_sec=10, max_retries=0)
            try:
                ok, message = backend.test_connection()
                self.finished.emit(ok, message)
            finally:
                backend.close()
        except Exception as exc:  # noqa: BLE001
            self.finished.emit(False, str(exc))


class ProviderCard(QFrame):
    """One provider row with status, key input, and actions."""

    changed = Signal()

    def __init__(self, entry: dict, config: dict):
        super().__init__()
        self.entry = entry
        self.config = config
        self.env_key = entry.get("env_key", "")
        self.provider_name = entry.get("name", "unknown")
        self.base_url = entry.get("base_url", "")
        self.model = entry.get("model", "")
        self._worker = None

        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)

        # Header: name + status
        header = QHBoxLayout()
        name_label = QLabel(f"<b>{self.provider_name}</b>")
        header.addWidget(name_label)
        header.addStretch()
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color: #888; font-size: 14px;")
        header.addWidget(self.status_dot)
        self.status_text = QLabel()
        self.status_text.setStyleSheet("color: #888;")
        header.addWidget(self.status_text)
        layout.addLayout(header)

        # Model line
        model_label = QLabel(f"<small>{self.model}</small>")
        model_label.setStyleSheet("color: #666;")
        layout.addWidget(model_label)

        # Key row
        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("Key:"))
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText("paste API key")
        existing = resolve_key(self.env_key)
        if existing:
            self.key_input.setText(existing)
            self.key_input.setPlaceholderText("(stored)")
        key_row.addWidget(self.key_input)
        layout.addLayout(key_row)

        # Button row
        btn_row = QHBoxLayout()
        self.save_btn = QPushButton("Save key")
        self.save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self.save_btn)

        self.test_btn = QPushButton("Test")
        self.test_btn.clicked.connect(self._on_test)
        btn_row.addWidget(self.test_btn)

        self.remove_btn = QPushButton("Remove")
        self.remove_btn.clicked.connect(self._on_remove)
        btn_row.addWidget(self.remove_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._refresh_status()

    # ---------- actions ----------

    def _on_save(self):
        value = self.key_input.text().strip()
        if not value:
            self._set_status("error", "empty key")
            return
        if set_cloud_key(self.env_key, value):
            self._set_status("ready", "saved")
            self.changed.emit()
        else:
            self._set_status("error", "save failed")

    def _on_remove(self):
        import os

        # Try keyring first
        removed_from_keyring = delete_cloud_key(self.env_key)

        # Clear the input regardless — user clicked Remove, they expect empty
        self.key_input.clear()
        self.key_input.setPlaceholderText("paste API key")

        # Warn if an env var will keep supplying the key on next launch
        env_value = os.environ.get(self.env_key, "")
        if env_value:
            self._set_status(
                "error",
                f"cleared; env var {self.env_key} still set",
            )
        elif removed_from_keyring:
            self._set_status("no_key", "removed")
        else:
            self._set_status("no_key", "cleared")

        self.changed.emit()

    def _on_test(self):
        key = self.key_input.text().strip() or resolve_key(self.env_key)
        if not key:
            self._set_status("error", "no key to test")
            return

        self.test_btn.setEnabled(False)
        self._set_status("unknown", "testing…")

        self._worker = ConnectionTestWorker(
            self.provider_name, self.base_url, self.model, key
        )
        self._worker.finished.connect(self._on_test_finished)
        self._worker.start()

    def _on_test_finished(self, ok: bool, message: str):
        self.test_btn.setEnabled(True)
        if ok:
            self._set_status("ready", "connection ok")
        else:
            self._set_status("error", message[:60])

    # ---------- internals ----------

    def _refresh_status(self):
        key = resolve_key(self.env_key)
        if not key:
            self._set_status("no_key", "no key")
        else:
            self._set_status("ready", "ready")

    def _set_status(self, state: str, text: str):
        color = STATUS_COLORS.get(state, STATUS_COLORS["unknown"])
        self.status_dot.setStyleSheet(f"color: {color}; font-size: 14px;")
        self.status_text.setText(text)


class CloudPanel(QWidget):
    """Settings panel for cloud LLM configuration."""

    settings_changed = Signal()

    def __init__(self, config: dict, pool=None):
        super().__init__()
        self.config = config
        self.cfg = cloud_config(config)
        self.pool = pool

        layout = QVBoxLayout(self)

        title = QLabel("<h2>Cloud LLM</h2>")
        layout.addWidget(title)

        subtitle = QLabel(
            "Optional cloud acceleration for chat. Observation, memory, "
            "and insights always stay on-device."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(subtitle)

        # Enable toggle
        self.enable_cb = QCheckBox("Enable cloud LLM")
        self.enable_cb.setChecked(bool(self.cfg.get("enabled", False)))
        self.enable_cb.stateChanged.connect(self._on_enable_changed)
        layout.addWidget(self.enable_cb)

        # Scrollable provider list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)

        for entry in self.cfg.get("providers") or []:
            card = ProviderCard(entry, self.cfg)
            card.changed.connect(self._on_provider_changed)
            inner_layout.addWidget(card)

        inner_layout.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll)

        # Fallback toggle
        self.fallback_cb = QCheckBox("Use local model when cloud is unavailable")
        self.fallback_cb.setChecked(bool(self.cfg.get("fallback_to_local", True)))
        layout.addWidget(self.fallback_cb)

        # Save button
        save_row = QHBoxLayout()
        save_row.addStretch()
        self.save_btn = QPushButton("Save and close")
        self.save_btn.clicked.connect(self._on_save)
        save_row.addWidget(self.save_btn)
        layout.addLayout(save_row)

    # ---------- actions ----------

    def _on_enable_changed(self, state):
        self.cfg["enabled"] = state == 2

    def _on_provider_changed(self):
        self.settings_changed.emit()

    def _on_save(self):
        from shadow.config import save_cloud_settings

        enabled = self.enable_cb.isChecked()
        fallback = self.fallback_cb.isChecked()

        if save_cloud_settings("config.yaml", enabled, fallback):
            self.config.setdefault("cloud", {})["enabled"] = enabled
            self.config["cloud"]["fallback_to_local"] = fallback
            self.settings_changed.emit()
