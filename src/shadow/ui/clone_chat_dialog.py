"""Chat with one clone — mandatory simulation labeling (C11)."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
)

from shadow.agent.shadow_cloning import CloneSession

SIMULATION_BANNER = (
    "SIMULATION — not part of your memory. "
    "Nothing here is stored as an observation or fact."
)


class _ReplyWorker(QThread):
    finished_with = Signal(object)
    failed = Signal(str)

    def __init__(self, session, backend, text) -> None:
        super().__init__()
        self._session = session
        self._backend = backend
        self._text = text

    def run(self) -> None:
        try:
            artifact = self._session.generate_reply(self._backend, self._text)
            self.finished_with.emit(artifact)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class CloneChatDialog(QDialog):
    def __init__(self, session: CloneSession, backend, manager=None, parent=None):
        super().__init__(parent)
        self._session = session
        self._backend = backend
        self._manager = manager
        self._worker = None
        self._selected_artifact = None
        self.setWindowTitle(f"Clone: {session.name}")
        self.resize(760, 620)
        self._build_ui()
        self._render()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        self._banner = QLabel(SIMULATION_BANNER, self)
        self._banner.setWordWrap(True)
        self._banner.setStyleSheet(
            "background: #fff4e5; border: 1px solid #f0b400; "
            "padding: 8px; border-radius: 4px; color: #6b4e00; font-weight: 600;"
        )
        root.addWidget(self._banner)

        self._feed = QTextBrowser(self)
        self._feed.setOpenLinks(False)
        self._feed.anchorClicked.connect(self._on_link)
        root.addWidget(self._feed, 1)

        input_row = QHBoxLayout()
        self._input = QTextEdit(self)
        self._input.setPlaceholderText(
            "Ask a what-if question. Everything stays isolated in this clone."
        )
        self._input.setMaximumHeight(80)
        input_row.addWidget(self._input, 1)

        col = QVBoxLayout()
        self._send_btn = QPushButton("Send", self)
        self._send_btn.setDefault(True)
        self._send_btn.clicked.connect(self._on_send)
        col.addWidget(self._send_btn)
        self._copy_btn = QPushButton("Copy", self)
        self._copy_btn.setEnabled(False)
        self._copy_btn.clicked.connect(self._on_copy)
        col.addWidget(self._copy_btn)
        input_row.addLayout(col)
        root.addLayout(input_row)

        footer = QHBoxLayout()
        self._status = QLabel(self)
        self._status.setStyleSheet("color: #888; font-size: 11px;")
        footer.addWidget(self._status)
        footer.addStretch(1)
        self._discard_btn = QPushButton("Discard clone", self)
        self._discard_btn.setStyleSheet("color: #b00020;")
        self._discard_btn.clicked.connect(self._on_discard)
        footer.addWidget(self._discard_btn)
        close_btn = QPushButton("Close", self)
        close_btn.clicked.connect(self.reject)
        footer.addWidget(close_btn)
        root.addLayout(footer)

    def _render(self) -> None:
        feed = self._session.feed()
        if not feed:
            self._feed.setHtml("<i>No messages yet. Ask a what-if question below.</i>")
            self._status.setText("0 messages · 0 artifacts")
            return
        parts: list[str] = []
        for item in feed:
            if item["kind"] == "message":
                who = "You" if item["role"] == "user" else "Shadow"
                parts.append(f"<p><b>{who}:</b> {_escape(item['text'])}</p>")
            else:
                aid = item["artifact_id"]
                parts.append(
                    f"<hr><p style='color:#6b4e00'>"
                    f"<b>SIMULATION</b> (artifact {aid[:8]}) "
                    f"<a href='copy:{aid}'>[copy]</a> "
                    f"<a href='promote:{aid}'>[promote to memory]</a></p>"
                    f"<p>{_escape(item['text'])}</p>"
                )
        self._feed.setHtml("".join(parts))
        self._feed.verticalScrollBar().setValue(
            self._feed.verticalScrollBar().maximum()
        )
        self._status.setText(
            f"{len(self._session.list_messages())} messages · "
            f"{len(self._session.list_artifacts())} artifacts"
        )

    def _on_send(self) -> None:
        text = self._input.toPlainText().strip()
        if not text:
            return
        self._input.clear()
        self._send_btn.setEnabled(False)
        self._worker = _ReplyWorker(self._session, self._backend, text)
        self._worker.finished_with.connect(self._on_done)
        self._worker.failed.connect(self._on_fail)
        self._worker.start()

    def _on_done(self, _artifact) -> None:
        self._send_btn.setEnabled(True)
        self._render()

    def _on_fail(self, _msg) -> None:
        self._send_btn.setEnabled(True)
        self._render()

    def _on_link(self, url) -> None:
        s = url.toString()
        if s.startswith("copy:"):
            aid = s[5:]
            for a in self._session.list_artifacts():
                if a["artifact_id"] == aid:
                    self._selected_artifact = a
                    self._copy_btn.setEnabled(True)
                    self._on_copy()
                    return
        elif s.startswith("promote:"):
            self._on_promote(s[8:])

    def _on_promote(self, artifact_id: str) -> None:
        from shadow.agent.shadow_cloning import DuplicatePromotionError

        art = next(
            (
                a
                for a in self._session.list_artifacts()
                if a["artifact_id"] == artifact_id
            ),
            None,
        )
        if art is None:
            return

        preview = art["text"][:200]
        if len(art["text"]) > 200:
            preview += "…"
        confirm = QMessageBox.question(
            self,
            "Promote to memory",
            f"Save this simulated output as a real note in your memory?\n\n"
            f'"{preview}"\n\n'
            "It will be marked 'promoted from a clone' in your memory and "
            "will be searchable alongside your normal observations.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        try:
            note_ref = self._session.promote(artifact_id, backend=self._backend)
        except DuplicatePromotionError:
            QMessageBox.information(
                self,
                "Already promoted",
                "This output has already been promoted to your memory.",
            )
            return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self,
                "Promote failed",
                f"Could not promote: {exc}",
            )
            return

        QMessageBox.information(
            self,
            "Promoted",
            f"Saved as note #{note_ref}. It's now part of your memory.",
        )

    def _on_copy(self) -> None:
        a = self._selected_artifact
        if a is None:
            return
        QApplication.clipboard().setText(
            f"SIMULATION (not part of memory):\n{a['text']}"
        )

    def _on_discard(self) -> None:
        if self._manager is not None:
            self._manager.discard(self._session.clone_id)
        else:
            self._session.discard()
        self.accept()


def _escape(t) -> str:
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
