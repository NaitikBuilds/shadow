from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class InsightPanel(QWidget):
    """Displays a list of Insight objects as cards.

    Consulted through FocusShield so deep-work sessions only surface
    high-confidence insights.
    """

    def __init__(self, recovery_engine, focus_shield=None):
        super().__init__()
        self.recovery_engine = recovery_engine
        self.focus_shield = focus_shield

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Insights</h2>"))

        self.focus_label = QLabel()
        self.focus_label.setStyleSheet("color: #888; padding: 2px 0;")
        layout.addWidget(self.focus_label)

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

        state = "normal"
        if self.focus_shield is not None:
            try:
                state = self.focus_shield.current_state().value
                insights = self.focus_shield.filter(insights)
            except Exception:
                state = "normal"

        self.focus_label.setText(f"Focus state: {state}")

        if not insights:
            text = "No insights right now."
            if state == "focused":
                text = "Focus mode active — only high-confidence insights shown."
            empty = QLabel(text)
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
