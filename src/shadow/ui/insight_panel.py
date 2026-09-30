from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class InsightPanel(QWidget):
    """Displays a list of Insight objects as cards."""

    def __init__(self, recovery_engine):
        super().__init__()
        self.recovery_engine = recovery_engine

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Insights</h2>"))

        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        layout.addWidget(refresh)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.inner = QWidget()
        self.inner_layout = QVBoxLayout(self.inner)
        self.scroll.setWidget(self.inner)
        layout.addWidget(self.scroll)

        self.refresh()

    def refresh(self):
        while self.inner_layout.count():
            item = self.inner_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        try:
            insights = self.recovery_engine.find_unfinished()
        except Exception:
            insights = []

        if not insights:
            empty = QLabel("No insights right now.")
            empty.setStyleSheet("color: #888; padding: 12px;")
            self.inner_layout.addWidget(empty)
            self.inner_layout.addStretch()
            return

        for insight in insights:
            self.inner_layout.addWidget(self._make_card(insight))
        self.inner_layout.addStretch()

    @staticmethod
    def _make_card(insight) -> QWidget:
        card = QFrame()
        card.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(card)

        title = QLabel(f"<b>{insight.title}</b>")
        title.setWordWrap(True)
        layout.addWidget(title)

        body = QLabel(insight.body)
        body.setWordWrap(True)
        body.setStyleSheet("color: #666;")
        layout.addWidget(body)

        meta = QLabel(f"<small>score {insight.score:.2f} · {insight.kind}</small>")
        meta.setStyleSheet("color: #999;")
        layout.addWidget(meta)

        if insight.action:
            action = QLabel(f"<i>{insight.action}</i>")
            action.setStyleSheet("color: #4a90e2;")
            layout.addWidget(action)

        return card
