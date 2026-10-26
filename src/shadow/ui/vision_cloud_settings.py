"""Settings for opt-in cloud vision."""

import yaml
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from shadow.config import ROOT


class VisionCloudSettingsPanel(QWidget):
    """Configure cloud vision without modifying text-cloud settings."""

    settings_changed = Signal()

    def __init__(self, config: dict, memory, config_path: str = "config.yaml"):
        super().__init__()

        self.config = config
        self.memory = memory
        self.config_path = ROOT / config_path

        vision_cfg = config.get("vision") or {}
        cloud_cfg = vision_cfg.get("cloud") or {}
        text_cloud_cfg = config.get("cloud") or {}

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("<h2>Vision Cloud</h2>"))

        explanation = QLabel(
            "Local vision processes screenshots on your device. "
            "Cloud vision sends the selected screenshot to a configured "
            "provider. Cloud vision is independent of cloud chat. "
            "Background and continuous vision remain local-only."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        self.enabled_cb = QCheckBox("Enable cloud vision")
        self.enabled_cb.setChecked(bool(cloud_cfg.get("enabled", False)))
        layout.addWidget(self.enabled_cb)

        self.fallback_cb = QCheckBox(
            "Use local Moondream vision if cloud analysis fails"
        )
        self.fallback_cb.setChecked(bool(cloud_cfg.get("fallback_to_local", True)))
        layout.addWidget(self.fallback_cb)

        self.preview_cb = QCheckBox("Require preview approval before sending an image")
        self.preview_cb.setChecked(bool(cloud_cfg.get("require_preview", True)))
        layout.addWidget(self.preview_cb)

        layout.addWidget(QLabel("<b>Vision provider priority</b>"))

        self.providers_list = QListWidget()

        provider_entries = text_cloud_cfg.get("providers") or []
        configured_names = [
            str(name).lower() for name in cloud_cfg.get("providers", ["gemini"])
        ]

        for entry in sorted(
            provider_entries,
            key=lambda item: item.get("priority", 99),
        ):
            name = str(entry.get("name", "")).strip()
            if not name:
                continue

            item = QListWidgetItem(name)
            item.setFlags(
                item.flags()
                | item.flags().__class__.ItemIsUserCheckable
                | item.flags().__class__.ItemIsEnabled
                | item.flags().__class__.ItemIsSelectable
            )
            item.setCheckState(
                Qt.CheckState.Checked
                if name.lower() in configured_names
                else Qt.CheckState.Unchecked
            )
            self.providers_list.addItem(item)

        layout.addWidget(self.providers_list)

        reorder = QHBoxLayout()

        up_btn = QPushButton("Move up")
        up_btn.clicked.connect(lambda: self._move_selected(-1))
        reorder.addWidget(up_btn)

        down_btn = QPushButton("Move down")
        down_btn.clicked.connect(lambda: self._move_selected(1))
        reorder.addWidget(down_btn)

        layout.addLayout(reorder)

        privacy_note = QLabel(
            "Cloud vision requires the separate vision_cloud consent "
            "channel. An API key alone never grants permission to upload "
            "screenshots. Sensitive-window exclusions always apply."
        )
        privacy_note.setWordWrap(True)
        privacy_note.setStyleSheet("color: #888;")
        layout.addWidget(privacy_note)

        save_btn = QPushButton("Save Vision Settings")
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)

    def _move_selected(self, offset: int):
        row = self.providers_list.currentRow()
        target = row + offset

        if row < 0 or target < 0 or target >= self.providers_list.count():
            return

        item = self.providers_list.takeItem(row)
        self.providers_list.insertItem(target, item)
        self.providers_list.setCurrentRow(target)

    def _save(self):
        selected_providers = []

        for index in range(self.providers_list.count()):
            item = self.providers_list.item(index)
            if item.checkState() == 2:
                selected_providers.append(item.text().lower())

        if self.enabled_cb.isChecked() and not selected_providers:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(
                self,
                "No vision provider selected",
                "Select at least one provider before enabling cloud vision.",
            )
            return

        try:
            with self.config_path.open("r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}

            vision = data.setdefault("vision", {})
            cloud = vision.setdefault("cloud", {})

            cloud["enabled"] = self.enabled_cb.isChecked()
            cloud["fallback_to_local"] = self.fallback_cb.isChecked()
            cloud["require_preview"] = self.preview_cb.isChecked()
            cloud["providers"] = selected_providers

            with self.config_path.open("w", encoding="utf-8") as handle:
                yaml.safe_dump(
                    data,
                    handle,
                    sort_keys=False,
                    allow_unicode=True,
                )

            # Update the in-memory config as well.
            current_vision = self.config.setdefault("vision", {})
            current_cloud = current_vision.setdefault("cloud", {})
            current_cloud.update(cloud)

            # Enabling the feature is not sufficient by itself to bypass
            # the separate consent channel. Consent is explicitly checked
            # and managed through the existing consent UI.
            self.settings_changed.emit()

        except (OSError, yaml.YAMLError) as exc:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(
                self,
                "Could not save vision settings",
                f"Settings were not saved: {type(exc).__name__}",
            )
