"""Settings panel for per-app vision exclusions."""

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class VisionExclusionsPanel(QWidget):
    """Manage the persistent vision exclusion list."""

    def __init__(self, store):
        super().__init__()
        self.store = store

        layout = QVBoxLayout(self)

        title = QLabel("<h2>Vision exclusions</h2>")
        layout.addWidget(title)

        subtitle = QLabel(
            "SHADOW will never analyze these apps, even when you press "
            "Ctrl+Shift+V. Password managers and banking apps are always "
            "excluded regardless of this list."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(subtitle)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("process name (e.g. slack.exe or slack)")
        row.addWidget(self.input)

        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add)
        row.addWidget(add_btn)
        layout.addLayout(row)

        action_row = QHBoxLayout()
        remove_btn = QPushButton("Remove selected")
        remove_btn.clicked.connect(self._remove_selected)
        action_row.addWidget(remove_btn)

        clear_btn = QPushButton("Remove all")
        clear_btn.clicked.connect(self._clear_all)
        action_row.addWidget(clear_btn)

        action_row.addStretch()
        layout.addLayout(action_row)

        self.refresh()

    # ---------- public API ----------

    def refresh(self):
        self.list_widget.clear()
        for entry in self.store.all_excluded():
            label = entry["process"]
            if entry.get("reason") and entry["reason"] != "user":
                label += f"  ({entry['reason']})"
            item = QListWidgetItem(label)
            item.setData(0x0100, entry["process"])  # Qt.UserRole
            self.list_widget.addItem(item)

    # ---------- actions ----------

    def _add(self):
        text = self.input.text().strip()
        if not text:
            return
        self.store.exclude(text, reason="user")
        self.input.clear()
        self.refresh()

    def _remove_selected(self):
        for item in self.list_widget.selectedItems():
            process = item.data(0x0100)
            if process:
                self.store.include(process)
        self.refresh()

    def _clear_all(self):
        self.store.clear_all()
        self.refresh()
