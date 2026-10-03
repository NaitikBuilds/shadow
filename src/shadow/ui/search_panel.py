"""Search panel — query observations with keyword + filters."""

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class SearchPanel(QWidget):
    """Search interface over observations."""

    def __init__(self, memory):
        super().__init__()
        self.memory = memory
        self._build_ui()
        self._populate_sources()

    # ---------- UI ----------

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Query row
        query_row = QHBoxLayout()
        query_row.addWidget(QLabel("Search:"))
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Type to search observations…")
        self.query_input.returnPressed.connect(self.run_search)
        query_row.addWidget(self.query_input)
        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self.run_search)
        query_row.addWidget(self.search_btn)
        layout.addLayout(query_row)

        # Filters row
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Source:"))
        self.source_combo = QComboBox()
        self.source_combo.addItem("Any", None)
        filter_row.addWidget(self.source_combo)

        filter_row.addWidget(QLabel("Entity:"))
        self.entity_input = QLineEdit()
        self.entity_input.setPlaceholderText("e.g. SHADOW")
        self.entity_input.setMaximumWidth(180)
        filter_row.addWidget(self.entity_input)

        filter_row.addStretch()
        layout.addLayout(filter_row)

        # Date row
        date_row = QHBoxLayout()
        date_row.addWidget(QLabel("From:"))
        self.from_date = QDateEdit()
        self.from_date.setCalendarPopup(True)
        self.from_date.setDate(QDate.currentDate().addDays(-7))
        self.from_date.setSpecialValueText("Any")
        self.from_date.setMinimumDate(QDate(2000, 1, 1))
        date_row.addWidget(self.from_date)

        date_row.addWidget(QLabel("To:"))
        self.to_date = QDateEdit()
        self.to_date.setCalendarPopup(True)
        self.to_date.setDate(QDate.currentDate())
        date_row.addWidget(self.to_date)

        clear_btn = QPushButton("Clear filters")
        clear_btn.clicked.connect(self.clear_filters)
        date_row.addWidget(clear_btn)
        date_row.addStretch()
        layout.addLayout(date_row)

        # Status line
        self.status = QLabel("Enter a query and press Search.")
        self.status.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.status)

        # Results
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.results_inner = QWidget()
        self.results_layout = QVBoxLayout(self.results_inner)
        self.scroll.setWidget(self.results_inner)
        layout.addWidget(self.scroll)

    def _populate_sources(self):
        try:
            sources = self.memory.distinct_sources()
        except Exception:
            sources = []
        for src in sources:
            self.source_combo.addItem(src, src)

    # ---------- actions ----------

    def clear_filters(self):
        self.query_input.clear()
        self.entity_input.clear()
        self.source_combo.setCurrentIndex(0)
        self.from_date.setDate(QDate.currentDate().addDays(-7))
        self.to_date.setDate(QDate.currentDate())
        self._clear_results()
        self.status.setText("Filters cleared.")

    def run_search(self):
        query = self.query_input.text().strip()
        source = self.source_combo.currentData()
        entity = self.entity_input.text().strip() or None

        start = self.from_date.date().toString("yyyy-MM-dd") + " 00:00:00"
        end = self.to_date.date().toString("yyyy-MM-dd") + " 23:59:59"

        try:
            rows = self.memory.search_observations(
                query=query,
                source=source,
                entity_name=entity,
                start=start,
                end=end,
                limit=100,
            )
        except Exception as exc:
            self.status.setText(f"Search failed: {exc}")
            return

        self._clear_results()

        if not rows:
            self.status.setText("No matches.")
            return

        self.status.setText(f"{len(rows)} matches.")
        for obs_id, ts, src, content in rows:
            self.results_layout.addWidget(
                self._make_card(obs_id, ts, src, content or "")
            )
        self.results_layout.addStretch()

    # ---------- rendering ----------

    def _clear_results(self):
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _make_card(self, obs_id: int, ts: str, source: str, content: str) -> QWidget:
        card = QFrame()
        card.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(card)

        header = QLabel(f"<b>[{ts}]</b> &nbsp;<code>{source}</code>")
        header.setStyleSheet("color: #666;")
        layout.addWidget(header)

        body_text = content.strip()
        if len(body_text) > 400:
            body_text = body_text[:400] + "…"
        body = QLabel(body_text)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(body)

        return card
