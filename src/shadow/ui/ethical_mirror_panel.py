"""Ethical Mirror settings panel (C08).

QWidget panel, opened inside a QDialog from MainWindow (same pattern
as cloud_panel, consent_panel, ambient_panel). Hosts:

  - Limited-profile banner when < 10 active values
  - Opted-out banner when user disabled the feature
  - Active values list (edit / archive / delete / reorder)
  - Archived values list (restore / delete permanently)
  - Add-new button
  - Replay-onboarding button
  - Delete-all (with confirmation)
  - Opt-out toggle
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from shadow.agent.ethical_mirror import (
    COMPLETE_PROFILE_MIN,
    EthicalValueDuplicateError,
    EthicalValuesStore,
    EthicalValueValidationError,
)


class EthicalMirrorPanel(QWidget):
    """Values manager. Emits `wizard_requested` when the user asks to replay
    onboarding, and `values_changed` after any mutation."""

    wizard_requested = Signal()
    values_changed = Signal()

    def __init__(self, memory, config=None, parent=None) -> None:
        super().__init__(parent)
        self._memory = memory
        self._config = config
        self._store = EthicalValuesStore(memory)
        self._build_ui()
        self._refresh()

    # ---- UI --------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        self._banner = QLabel(self)
        self._banner.setWordWrap(True)
        self._banner.setStyleSheet(
            "background: #fff4e5; border: 1px solid #f0b400; "
            "padding: 8px; border-radius: 4px; color: #6b4e00;"
        )
        self._banner.hide()
        root.addWidget(self._banner)

        self._tabs = QTabWidget(self)
        root.addWidget(self._tabs, 1)

        # --- Active tab ---
        active_wrap = QWidget()
        active_layout = QVBoxLayout(active_wrap)
        active_layout.setContentsMargins(0, 0, 0, 0)

        self._active_scroll = QScrollArea()
        self._active_scroll.setWidgetResizable(True)
        self._active_container = QWidget()
        self._active_rows = QVBoxLayout(self._active_container)
        self._active_rows.setAlignment(Qt.AlignTop)
        self._active_scroll.setWidget(self._active_container)
        active_layout.addWidget(self._active_scroll, 1)

        add_row = QHBoxLayout()
        self._add_btn = QPushButton("+ Add new value", self)
        self._add_btn.clicked.connect(self._on_add)
        add_row.addWidget(self._add_btn)
        add_row.addStretch(1)
        active_layout.addLayout(add_row)

        self._tabs.addTab(active_wrap, "Active")

        # --- Archived tab ---
        archived_wrap = QWidget()
        archived_layout = QVBoxLayout(archived_wrap)
        archived_layout.setContentsMargins(0, 0, 0, 0)

        self._archived_scroll = QScrollArea()
        self._archived_scroll.setWidgetResizable(True)
        self._archived_container = QWidget()
        self._archived_rows = QVBoxLayout(self._archived_container)
        self._archived_rows.setAlignment(Qt.AlignTop)
        self._archived_scroll.setWidget(self._archived_container)
        archived_layout.addWidget(self._archived_scroll, 1)

        self._tabs.addTab(archived_wrap, "Archived")

        # --- footer actions ---
        footer = QHBoxLayout()
        self._replay_btn = QPushButton("Replay onboarding", self)
        self._replay_btn.clicked.connect(self._on_replay)
        footer.addWidget(self._replay_btn)

        self._optout_btn = QPushButton(self)
        self._optout_btn.clicked.connect(self._on_toggle_optout)
        footer.addWidget(self._optout_btn)

        footer.addStretch(1)

        self._delete_all_btn = QPushButton("Delete all values", self)
        self._delete_all_btn.setStyleSheet("color: #b00020; padding: 4px 10px;")
        self._delete_all_btn.clicked.connect(self._on_delete_all)
        footer.addWidget(self._delete_all_btn)

        root.addLayout(footer)

    # ---- refresh ---------------------------------------------------------
    def _refresh(self) -> None:
        self._refresh_banner()
        self._refresh_active()
        self._refresh_archived()
        self._refresh_footer_labels()

    def _refresh_banner(self) -> None:
        if self._store.is_opted_out():
            self._banner.setText(
                "Ethical Mirror is turned off. Your values are still stored "
                "locally. Re-enable any time with the button below."
            )
            self._banner.show()
            self._tabs.setEnabled(False)
            self._add_btn.setEnabled(False)
            return

        self._tabs.setEnabled(True)
        self._add_btn.setEnabled(True)

        n = self._store.count_active()
        if self._store.is_limited_mode():
            self._banner.setText(
                f"Limited profile: {n} of {COMPLETE_PROFILE_MIN} values. "
                "Add more for stronger reflections."
            )
            self._banner.show()
        else:
            self._banner.hide()

    def _refresh_active(self) -> None:
        while self._active_rows.count():
            item = self._active_rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        values = self._store.list_active()
        if not values:
            empty = QLabel("No values yet. Click “Add new value” to begin.", self)
            empty.setStyleSheet("color: #888; padding: 16px;")
            self._active_rows.addWidget(empty)
            return

        for i, v in enumerate(values):
            self._active_rows.addWidget(self._make_value_row(v, i, len(values)))

    def _refresh_archived(self) -> None:
        while self._archived_rows.count():
            item = self._archived_rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        values = self._store.list_archived()
        if not values:
            empty = QLabel("No archived values.", self)
            empty.setStyleSheet("color: #888; padding: 16px;")
            self._archived_rows.addWidget(empty)
            return
        for v in values:
            self._archived_rows.addWidget(self._make_archived_row(v))

    def _refresh_footer_labels(self) -> None:
        self._optout_btn.setText(
            "Re-enable Ethical Mirror"
            if self._store.is_opted_out()
            else "Turn off Ethical Mirror"
        )

    def _make_value_row(self, v: dict, idx: int, total: int) -> QWidget:
        row = QFrame(self)
        row.setStyleSheet(
            "QFrame { border: 1px solid #e0e0e0; border-radius: 4px; "
            "padding: 6px; margin: 2px; }"
        )
        layout = QHBoxLayout(row)
        layout.setContentsMargins(6, 4, 6, 4)

        text = QLabel(v["text"], row)
        text.setWordWrap(True)
        layout.addWidget(text, 1)

        up = QPushButton("↑", row)
        up.setFixedWidth(28)
        up.setEnabled(idx > 0)
        up.clicked.connect(lambda: self._on_move(idx, -1))
        layout.addWidget(up)

        down = QPushButton("↓", row)
        down.setFixedWidth(28)
        down.setEnabled(idx < total - 1)
        down.clicked.connect(lambda: self._on_move(idx, +1))
        layout.addWidget(down)

        edit = QPushButton("Edit", row)
        edit.clicked.connect(lambda: self._on_edit(v))
        layout.addWidget(edit)

        archive = QPushButton("Archive", row)
        archive.clicked.connect(lambda: self._on_archive(v["value_id"]))
        layout.addWidget(archive)

        delete = QPushButton("Delete", row)
        delete.clicked.connect(lambda: self._on_delete(v["value_id"]))
        layout.addWidget(delete)

        return row

    def _make_archived_row(self, v: dict) -> QWidget:
        row = QFrame(self)
        row.setStyleSheet(
            "QFrame { border: 1px solid #eee; border-radius: 4px; "
            "padding: 6px; margin: 2px; background: #fafafa; }"
        )
        layout = QHBoxLayout(row)
        layout.setContentsMargins(6, 4, 6, 4)

        text = QLabel(v["text"], row)
        text.setWordWrap(True)
        text.setStyleSheet("color: #666;")
        layout.addWidget(text, 1)

        restore = QPushButton("Restore", row)
        restore.clicked.connect(lambda: self._on_restore(v["value_id"]))
        layout.addWidget(restore)

        delete = QPushButton("Delete permanently", row)
        delete.clicked.connect(lambda: self._on_delete(v["value_id"]))
        layout.addWidget(delete)

        return row

    # ---- actions ---------------------------------------------------------
    def _on_add(self) -> None:
        text, ok = QInputDialog.getMultiLineText(
            self, "Add value", "Your value (1–300 characters):"
        )
        if not ok or not text.strip():
            return
        try:
            self._store.add(text.strip())
        except EthicalValueDuplicateError:
            QMessageBox.information(
                self,
                "Ethical Mirror",
                "A value with the same text already exists.",
            )
            return
        except EthicalValueValidationError as exc:
            QMessageBox.warning(self, "Ethical Mirror", str(exc))
            return
        self._refresh()
        self.values_changed.emit()

    def _on_edit(self, v: dict) -> None:
        text, ok = QInputDialog.getMultiLineText(
            self, "Edit value", "Update this value:", v["text"]
        )
        if not ok or not text.strip():
            return
        try:
            self._store.update(v["value_id"], text=text.strip())
        except EthicalValueDuplicateError:
            QMessageBox.information(
                self,
                "Ethical Mirror",
                "A value with the same text already exists.",
            )
            return
        except EthicalValueValidationError as exc:
            QMessageBox.warning(self, "Ethical Mirror", str(exc))
            return
        self._refresh()
        self.values_changed.emit()

    def _on_archive(self, value_id: int) -> None:
        self._store.archive(value_id)
        self._refresh()
        self.values_changed.emit()

    def _on_restore(self, value_id: int) -> None:
        try:
            self._store.restore(value_id)
        except EthicalValueDuplicateError as exc:
            QMessageBox.information(self, "Ethical Mirror", str(exc))
            return
        self._refresh()
        self.values_changed.emit()

    def _on_delete(self, value_id: int) -> None:
        if (
            QMessageBox.question(
                self,
                "Delete value",
                "Permanently delete this value?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        self._store.delete(value_id)
        self._refresh()
        self.values_changed.emit()

    def _on_move(self, idx: int, delta: int) -> None:
        values = self._store.list_active()
        if idx + delta < 0 or idx + delta >= len(values):
            return
        new_order = [v["value_id"] for v in values]
        new_order[idx], new_order[idx + delta] = new_order[idx + delta], new_order[idx]
        self._store.reorder(new_order)
        self._refresh()

    def _on_replay(self) -> None:
        self._store.reset_onboarding()
        self.wizard_requested.emit()

    def _on_toggle_optout(self) -> None:
        new_state = not self._store.is_opted_out()
        if (
            new_state
            and QMessageBox.question(
                self,
                "Turn off Ethical Mirror",
                "The panel will be disabled. Your values are kept and can be "
                "restored by re-enabling. Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        self._store.set_opt_out(new_state)
        self._refresh()

    def _on_delete_all(self) -> None:
        if (
            QMessageBox.question(
                self,
                "Delete all values",
                "Delete every value and its history? This cannot be undone.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        self._store.clear_all()
        self._refresh()
        self.values_changed.emit()
