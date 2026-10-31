"""Active clone list (C11)."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from shadow.agent.shadow_cloning import CloneManager


class CloneListDialog(QDialog):
    def __init__(self, manager: CloneManager, backend, parent=None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._backend = backend
        self.setWindowTitle("SHADOW — Clones")
        self.resize(620, 500)
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.addWidget(
            QLabel(
                "Clones are isolated what-if environments. They read your memory "
                "but never write to it. Anything they produce is a simulation.",
                self,
            )
        )
        self._list = QListWidget(self)
        root.addWidget(self._list, 1)

        row = QHBoxLayout()
        self._create_btn = QPushButton("+ Create clone", self)
        self._create_btn.clicked.connect(self._on_create)
        row.addWidget(self._create_btn)
        row.addStretch(1)
        self._open_btn = QPushButton("Open", self)
        self._open_btn.clicked.connect(self._on_open)
        row.addWidget(self._open_btn)
        self._discard_btn = QPushButton("Discard", self)
        self._discard_btn.setStyleSheet("color: #b00020;")
        self._discard_btn.clicked.connect(self._on_discard)
        row.addWidget(self._discard_btn)
        close_btn = QPushButton("Close", self)
        close_btn.clicked.connect(self.reject)
        row.addWidget(close_btn)
        root.addLayout(row)

    def _refresh(self) -> None:
        self._list.clear()
        rows = self._manager.list_active()
        for r in rows:
            ts = datetime.fromtimestamp(r["created_at"] / 1000).strftime(
                "%Y-%m-%d %H:%M"
            )
            it = QListWidgetItem(f"{r['name']}  ·  {ts}")
            it.setData(Qt.UserRole, r["clone_id"])
            self._list.addItem(it)
        has = len(rows) > 0
        self._open_btn.setEnabled(has)
        self._discard_btn.setEnabled(has)
        if not has:
            self._list.addItem("No active clones. Create one to begin.")

    def _selected_clone_id(self):
        it = self._list.currentItem()
        return it.data(Qt.UserRole) if it is not None else None

    def _on_create(self) -> None:
        from shadow.ui.clone_create_dialog import CloneCreateDialog

        dlg = CloneCreateDialog(self._manager, parent=self)
        if dlg.exec() == QDialog.Accepted:
            s = dlg.created_session()
            self._refresh()
            if s is not None:
                self._open_session(s)

    def _on_open(self) -> None:
        cid = self._selected_clone_id()
        if not cid:
            return
        s = self._manager.get(cid)
        if s is None:
            QMessageBox.information(
                self,
                "Clone expired",
                "This clone is no longer active.",
            )
            self._refresh()
            return
        self._open_session(s)

    def _open_session(self, session) -> None:
        from shadow.ui.clone_chat_dialog import CloneChatDialog

        dlg = CloneChatDialog(
            session,
            self._backend,
            manager=self._manager,
            parent=self,
        )
        dlg.exec()
        self._refresh()

    def _on_discard(self) -> None:
        cid = self._selected_clone_id()
        if not cid:
            return
        if (
            QMessageBox.question(
                self,
                "Discard clone",
                "Discard this clone? All its messages and artifacts will be deleted.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        self._manager.discard(cid)
        self._refresh()
