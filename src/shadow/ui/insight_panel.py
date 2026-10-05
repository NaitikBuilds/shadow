from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class InsightPanel(QWidget):
    """Displays a list of Insight objects as cards with feedback buttons."""

    def __init__(self, engines=None, focus_shield=None, feedback=None):
        super().__init__()
        self.engines = engines or []
        self.focus_shield = focus_shield
        self.feedback = feedback

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

    # ---------- rendering ----------

    def refresh(self):
        while self.inner_layout.count():
            item = self.inner_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        insights = []
        for engine in self.engines:
            try:
                if hasattr(engine, "suggest"):
                    insights.extend(engine.suggest())
                elif hasattr(engine, "find_notes"):
                    insights.extend(engine.find_notes())
                elif hasattr(engine, "find_stuck"):
                    insights.extend(engine.find_stuck())
                elif hasattr(engine, "find_recurring"):
                    insights.extend(engine.find_recurring())
                elif hasattr(engine, "find_patterns"):
                    insights.extend(engine.find_patterns())
                elif hasattr(engine, "find_decaying"):
                    insights.extend(engine.find_decaying())
                elif hasattr(engine, "forecast"):
                    insights.extend(engine.forecast())
                elif hasattr(engine, "find_unfinished"):
                    insights.extend(engine.find_unfinished())
            except Exception as exc:
                import traceback

                print(
                    f"[insight_panel] {type(engine).__name__} failed: {exc}",
                    flush=True,
                )
                traceback.print_exc()
                continue

        best = {}
        for i in insights:
            existing = best.get(i.title)
            if existing is None or i.score > existing.score:
                best[i.title] = i
        insights = sorted(best.values(), key=lambda i: i.score, reverse=True)

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

    def _make_card(self, insight) -> QWidget:
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

        # Feedback row
        fb_row = QHBoxLayout()
        fb_row.addStretch()

        prior = None
        if self.feedback is not None:
            try:
                prior = self.feedback.verdict_for(insight.kind, insight.title)
            except Exception:
                prior = None

        status = QLabel()
        if prior:
            status.setText(
                "✓ marked useful" if prior == "useful" else "✗ marked not useful"
            )
            status.setStyleSheet("color: #888; font-size: 10px;")
            fb_row.addWidget(status)

        up = QPushButton("👍")
        up.setToolTip("Useful")
        up.setMaximumWidth(40)
        up.clicked.connect(lambda _, i=insight: self._feedback(i, "useful"))
        fb_row.addWidget(up)

        down = QPushButton("👎")
        down.setToolTip("Not useful")
        down.setMaximumWidth(40)
        down.clicked.connect(lambda _, i=insight: self._feedback(i, "not_useful"))
        fb_row.addWidget(down)

        layout.addLayout(fb_row)
        return card

    # ---------- feedback ----------

    def _feedback(self, insight, verdict: str):
        if self.feedback is None:
            return
        try:
            self.feedback.record(insight.kind, insight.title, verdict)
        except Exception:
            pass
        self.refresh()
