"""Weaver Insight Panel — Cross-Project Insights with Dismiss/Save/Restore.

Displays Weaver-generated cross-project insights as cards with feedback buttons.
Implements FR-P4-WVR-04, FR-P4-WVR-06, AC-P4-WVR-05.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from shadow.proactive.weaver_engine import CrossProjectInsight, WeaverEngine


class WeaverInsightPanel(QWidget):
    """Panel showing Weaver cross-project insights with Active/Dismissed tabs."""

    # Signal emitted when insight status changes (for external listeners)
    insight_status_changed = Signal(int, str)  # insight_id, new_status

    def __init__(self, weaver_engine: WeaverEngine, feedback=None):
        super().__init__()
        self.weaver_engine = weaver_engine
        self.feedback = feedback

        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Title
        layout.addWidget(QLabel("<h2>Cross-Project Insights</h2>"))

        # Tab widget: Active | Dismissed
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.North)

        # Active tab
        self.active_scroll = QScrollArea()
        self.active_scroll.setWidgetResizable(True)
        self.active_inner = QWidget()
        self.active_layout = QVBoxLayout(self.active_inner)
        self.active_scroll.setWidget(self.active_inner)
        self.tabs.addTab(self.active_scroll, "Active")

        # Dismissed tab
        self.dismissed_scroll = QScrollArea()
        self.dismissed_scroll.setWidgetResizable(True)
        self.dismissed_inner = QWidget()
        self.dismissed_layout = QVBoxLayout(self.dismissed_inner)
        self.dismissed_scroll.setWidget(self.dismissed_inner)
        self.tabs.addTab(self.dismissed_scroll, "Dismissed")

        layout.addWidget(self.tabs)

        # Refresh button
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        layout.addWidget(refresh)

    def refresh(self):
        """Reload insights from WeaverEngine and rebuild both tabs."""
        # Clear active tab
        while self.active_layout.count():
            item = self.active_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        # Clear dismissed tab
        while self.dismissed_layout.count():
            item = self.dismissed_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        # Fetch insights
        active_insights = self.weaver_engine.get_insights()
        dismissed_insights = self.weaver_engine.get_dismissed_insights()

        # Render active insights
        if not active_insights:
            empty = QLabel("No cross-project insights yet. Run Weaver to generate.")
            empty.setStyleSheet("color: #888; padding: 12px;")
            empty.setAlignment(Qt.AlignCenter)
            self.active_layout.addWidget(empty)
        else:
            for insight in active_insights:
                self.active_layout.addWidget(self._make_card(insight, is_dismissed=False))

        self.active_layout.addStretch()

        # Render dismissed insights
        if not dismissed_insights:
            empty = QLabel("No dismissed insights.")
            empty.setStyleSheet("color: #888; padding: 12px;")
            empty.setAlignment(Qt.AlignCenter)
            self.dismissed_layout.addWidget(empty)
        else:
            for insight in dismissed_insights:
                self.dismissed_layout.addWidget(self._make_card(insight, is_dismissed=True))

        self.dismissed_layout.addStretch()

    def _make_card(self, insight: CrossProjectInsight, is_dismissed: bool) -> QWidget:
        """Create a card widget for an insight."""
        card = QFrame()
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setStyleSheet("QFrame { border-radius: 6px; background: #fafafa; }")
        layout = QVBoxLayout(card)
        layout.setSpacing(6)
        layout.setContentsMargins(12, 10, 12, 10)

        # Header: projects + status badge
        header = QHBoxLayout()
        title = QLabel(f"<b>{insight.source_project}</b> \u2192 <b>{insight.target_project}</b>")
        title.setStyleSheet("font-size: 13px;")
        header.addWidget(title)
        header.addStretch()

        # Status badge
        status_badge = QLabel(insight.status.capitalize())
        status_badge.setStyleSheet(self._status_style(insight.status))
        header.addWidget(status_badge)
        layout.addLayout(header)

        # Statement
        body = QLabel(insight.statement)
        body.setWordWrap(True)
        body.setStyleSheet("color: #333; font-size: 12px;")
        layout.addWidget(body)

        # Meta: conflict flag, evidence count
        meta_parts = []
        if insight.conflict_flag:
            meta_parts.append("\u26a0 Conflicting evidence")
        evidence = insight.evidence
        src_count = len(evidence.get("source_evidence", []))
        tgt_count = len(evidence.get("target_evidence", []))
        meta_parts.append(f"Evidence: {src_count} + {tgt_count} observations")
        meta = QLabel("  \u00b7  ".join(meta_parts))
        meta.setStyleSheet("color: #888; font-size: 10px;")
        layout.addWidget(meta)

        # Feedback row
        fb_row = QHBoxLayout()
        fb_row.addStretch()

        # Prior feedback indicator
        if self.feedback is not None:
            try:
                prior = self.feedback.verdict_for("weaver", insight.statement)
            except Exception:
                prior = None
            if prior:
                status = QLabel("\u2713 Useful" if prior == "useful" else "\u2717 Not useful")
                status.setStyleSheet("color: #888; font-size: 10px;")
                fb_row.addWidget(status)

        # Action buttons
        if is_dismissed:
            # Restore button
            restore = QPushButton("Restore")
            restore.setToolTip("Move back to Active")
            restore.setMaximumWidth(80)
            restore.clicked.connect(lambda _, i=insight: self._on_restore(i))
            fb_row.addWidget(restore)

            # Permanently dismiss (cancel) button
            cancel = QPushButton("Cancel")
            cancel.setToolTip("Permanently remove")
            cancel.setMaximumWidth(80)
            cancel.setStyleSheet("color: #c00;")
            cancel.clicked.connect(lambda _, i=insight: self._on_cancel(i))
            fb_row.addWidget(cancel)
        else:
            # Save button (mark as saved - keeps in active but highlighted)
            save = QPushButton("Save")
            save.setToolTip("Mark as saved")
            save.setMaximumWidth(70)
            if insight.status == "saved":
                save.setText("Saved \u2713")
                save.setEnabled(False)
            save.clicked.connect(lambda _, i=insight: self._on_save(i))
            fb_row.addWidget(save)

            # Dismiss button
            dismiss = QPushButton("Dismiss")
            dismiss.setToolTip("Hide from Active, move to Dismissed")
            dismiss.setMaximumWidth(80)
            dismiss.clicked.connect(lambda _, i=insight: self._on_dismiss(i))
            fb_row.addWidget(dismiss)

            # Useful / Not useful buttons
            useful = QPushButton("\U0001f44d")
            useful.setToolTip("Useful")
            useful.setMaximumWidth(40)
            useful.clicked.connect(lambda _, i=insight: self._on_feedback(i, "useful"))
            fb_row.addWidget(useful)

            not_useful = QPushButton("\U0001f44e")
            not_useful.setToolTip("Not useful")
            not_useful.setMaximumWidth(40)
            not_useful.clicked.connect(lambda _, i=insight: self._on_feedback(i, "not_useful"))
            fb_row.addWidget(not_useful)

        layout.addLayout(fb_row)
        return card

    def _status_style(self, status: str) -> str:
        """Return stylesheet for status badge."""
        styles = {
            "new": "background: #e3f2fd; color: #1565c0; padding: 2px 8px; border-radius: 10px; font-size: 10px;",
            "saved": "background: #e8f5e9; color: #2e7d32; padding: 2px 8px; border-radius: 10px; font-size: 10px;",
            "dismissed": "background: #f5f5f5; color: #757575; padding: 2px 8px; border-radius: 10px; font-size: 10px;",
            "cancelled": "background: #fce4ec; color: #c62828; padding: 2px 8px; border-radius: 10px; font-size: 10px;",
            "stale": "background: #fff3e0; color: #ef6c00; padding: 2px 8px; border-radius: 10px; font-size: 10px;",
        }
        return styles.get(status, "padding: 2px 8px; border-radius: 10px; font-size: 10px;")

    # ---------- Action handlers ----------

    def _on_dismiss(self, insight: CrossProjectInsight):
        """Dismiss an insight: move to Dismissed tab."""
        if self.weaver_engine.dismiss_insight(insight.insight_id):
            self.insight_status_changed.emit(insight.insight_id, "dismissed")
            self.refresh()

    def _on_save(self, insight: CrossProjectInsight):
        """Save an insight: keep in Active with saved status."""
        if self.weaver_engine.save_insight(insight.insight_id):
            self.insight_status_changed.emit(insight.insight_id, "saved")
            self.refresh()

    def _on_restore(self, insight: CrossProjectInsight):
        """Restore a dismissed insight back to Active."""
        if self.weaver_engine.restore_insight(insight.insight_id):
            self.insight_status_changed.emit(insight.insight_id, "new")
            self.refresh()

    def _on_cancel(self, insight: CrossProjectInsight):
        """Permanently cancel/remove an insight."""
        if self.weaver_engine.cancel_insight(insight.insight_id):
            self.insight_status_changed.emit(insight.insight_id, "cancelled")
            self.refresh()

    def _on_feedback(self, insight: CrossProjectInsight, verdict: str):
        """Record useful/not_useful feedback."""
        if self.feedback is not None:
            try:
                self.feedback.record("weaver", insight.statement, verdict)
            except Exception:
                pass
        self.refresh()
