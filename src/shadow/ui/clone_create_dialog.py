"""Create-clone dialog (C11)."""

from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from shadow.agent.shadow_cloning import CloneManager


class CloneCreateDialog(QDialog):
    def __init__(self, manager: CloneManager, parent=None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._created_session = None
        self.setWindowTitle("Create clone")
        self.resize(520, 340)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        intro = QLabel(
            "A clone is an isolated read-only copy of your Shadow for what-if "
            "questions. Nothing it produces is added to your memory unless you "
            "explicitly promote it later.",
            self,
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        form = QFormLayout()
        self._name = QLineEdit(self)
        self._name.setMaxLength(60)
        self._name.setPlaceholderText("e.g. what if I quit?")
        form.addRow("Name:", self._name)

        now = datetime.now()
        self._start = QLineEdit(
            (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"),
            self,
        )
        form.addRow("Start:", self._start)
        self._end = QLineEdit(now.strftime("%Y-%m-%d %H:%M:%S"), self)
        form.addRow("End:", self._end)

        self._include_values = QCheckBox(
            "Include my Ethical Mirror values (read-only)",
            self,
        )
        form.addRow("", self._include_values)
        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            self,
        )
        buttons.accepted.connect(self._on_create)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _on_create(self) -> None:
        name = self._name.text().strip()
        start = self._start.text().strip()
        end = self._end.text().strip()

        for label, val in (("Start", start), ("End", end)):
            try:
                datetime.strptime(val, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                QMessageBox.warning(
                    self,
                    "Invalid date",
                    f"{label} must be YYYY-MM-DD HH:MM:SS",
                )
                return
        if start >= end:
            QMessageBox.warning(self, "Invalid range", "Start must be before End.")
            return

        try:
            session = self._manager.create(
                name=name,
                scope={"time_range": {"start": start, "end": end}},
                include_values=self._include_values.isChecked(),
            )
        except (ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "Cannot create clone", str(exc))
            return

        self._created_session = session
        self.accept()

    def created_session(self):
        return self._created_session
