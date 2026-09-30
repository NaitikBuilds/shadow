"""Ambient Task List panel — shows what SHADOW thinks you're working on."""

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class AmbientPanel(QWidget):
    """Displays the ambient task list with dismiss / promote / restore actions."""

    def __init__(self, ambient_list):
        super().__init__()
        self.ambient = ambient_list

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Working On</h2>"))

        subtitle = QLabel(
            "SHADOW noticed you've been engaging with these recently. "
            "Not a task manager — just a mirror."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(subtitle)

        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        layout.addWidget(refresh)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.inner = QWidget()
        self.inner_layout = QVBoxLayout(self.inner)
        self.scroll.setWidget(self.inner)
        layout.addWidget(self.scroll)

        self.dismissed_list = QListWidget()
        self.dismissed_list.setVisible(False)

        self.toggle_dismissed = QPushButton("Show dismissed")
        self.toggle_dismissed.clicked.connect(self._toggle_dismissed)
        layout.addWidget(self.toggle_dismissed)

        layout.addWidget(self.dismissed_list)

        self.refresh()

    # ---------- layout ----------

    def refresh(self):
        self._clear(self.inner_layout)

        try:
            tasks = self.ambient.list_active()
        except Exception:
            tasks = []

        if not tasks:
            empty = QLabel("Nothing right now.")
            empty.setStyleSheet("color: #888; padding: 12px;")
            self.inner_layout.addWidget(empty)
            self.inner_layout.addStretch()
        else:
            for task in tasks:
                self.inner_layout.addWidget(self._make_card(task))
            self.inner_layout.addStretch()

        self.dismissed_list.clear()
        try:
            for task in self.ambient.dismissed():
                self.dismissed_list.addItem(f"{task.name}  ({task.mentions} mentions)")
        except Exception:
            pass

    @staticmethod
    def _clear(layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _toggle_dismissed(self):
        visible = self.dismissed_list.isVisible()
        self.dismissed_list.setVisible(not visible)
        self.toggle_dismissed.setText(
            "Hide dismissed" if not visible else "Show dismissed"
        )

    # ---------- cards ----------

    def _make_card(self, task) -> QWidget:
        card = QFrame()
        card.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(card)

        title = QLabel(f"<b>{task.name}</b>")
        title.setWordWrap(True)
        layout.addWidget(title)

        meta = QLabel(
            f"<small>{task.entity_type} · {task.mentions} mentions · "
            f"score {task.score:.2f}"
            + ("  ·  ★ promoted" if task.promoted else "")
            + "</small>"
        )
        meta.setStyleSheet("color: #999;")
        layout.addWidget(meta)

        actions = QHBoxLayout()

        promote_btn = QPushButton("Promote")
        promote_btn.clicked.connect(lambda _, eid=task.entity_id: self._promote(eid))
        actions.addWidget(promote_btn)

        dismiss_btn = QPushButton("Dismiss")
        dismiss_btn.clicked.connect(lambda _, eid=task.entity_id: self._dismiss(eid))
        actions.addWidget(dismiss_btn)

        actions.addStretch()
        layout.addLayout(actions)

        return card

    # ---------- actions ----------

    def _dismiss(self, entity_id: int):
        try:
            self.ambient.dismiss(entity_id)
        except Exception:
            pass
        self.refresh()

    def _promote(self, entity_id: int):
        try:
            self.ambient.promote(entity_id)
        except Exception:
            pass
        self.refresh()
