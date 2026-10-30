"""Ethical Mirror — "Check against my values" dialog (C09).

Takes a decision context, runs the reflection on a background thread,
and renders the structured result. No save button (reflections are
ephemeral by design); a Copy button lets the user paste it elsewhere.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from shadow.agent.ethical_mirror import EthicalValuesStore
from shadow.agent.ethical_reflection import (
    EthicalReflector,
    Reflection,
    ReflectionUnavailable,
)


class _ReflectionWorker(QThread):
    finished_with = Signal(object)  # Reflection
    failed = Signal(str)

    def __init__(self, reflector: EthicalReflector, ctx: str) -> None:
        super().__init__()
        self._reflector = reflector
        self._ctx = ctx

    def run(self) -> None:  # noqa: D401
        try:
            result = self._reflector.reflect(self._ctx)
            self.finished_with.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class EthicalMirrorReflectDialog(QDialog):
    def __init__(self, memory, backend, parent=None) -> None:
        super().__init__(parent)
        self._memory = memory
        self._backend = backend
        self._store = EthicalValuesStore(memory)
        self._worker: _ReflectionWorker | None = None
        self._last: Reflection | None = None

        self.setWindowTitle("SHADOW — Check against my values")
        self.resize(700, 580)
        self._build_ui()

    # ---- UI --------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        intro = QLabel(
            "Describe a decision you're weighing. SHADOW will show which of "
            "your stated values touch on it — it will not tell you what to do.",
            self,
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #555;")
        root.addWidget(intro)

        self._input = QTextEdit(self)
        self._input.setPlaceholderText(
            "e.g. Should I take this project even though the timeline feels "
            "aggressive?"
        )
        self._input.setMaximumHeight(110)
        root.addWidget(self._input)

        self._limited_banner = QLabel(self)
        self._limited_banner.setWordWrap(True)
        self._limited_banner.setStyleSheet(
            "background: #fff4e5; border: 1px solid #f0b400; padding: 6px; "
            "border-radius: 4px; color: #6b4e00;"
        )
        self._limited_banner.hide()
        root.addWidget(self._limited_banner)

        self._result = QTextEdit(self)
        self._result.setReadOnly(True)
        root.addWidget(self._result, 1)

        buttons = QHBoxLayout()
        self._reflect_btn = QPushButton("Reflect", self)
        self._reflect_btn.setDefault(True)
        self._reflect_btn.clicked.connect(self._on_reflect)
        buttons.addWidget(self._reflect_btn)

        self._copy_btn = QPushButton("Copy result", self)
        self._copy_btn.setEnabled(False)
        self._copy_btn.clicked.connect(self._on_copy)
        buttons.addWidget(self._copy_btn)

        buttons.addStretch(1)

        self._close_btn = QPushButton("Close", self)
        self._close_btn.clicked.connect(self.reject)
        buttons.addWidget(self._close_btn)

        root.addLayout(buttons)

        self._status = QLabel(
            f"{self._store.count_active()} active value(s).",
            self,
        )
        self._status.setStyleSheet("color: #888; font-size: 11px;")
        root.addWidget(self._status)

    # ---- actions ---------------------------------------------------------
    def _on_reflect(self) -> None:
        ctx = self._input.toPlainText().strip()
        if not ctx:
            self._result.setHtml("<i>Describe a decision first.</i>")
            return

        try:
            reflector = EthicalReflector(self._store, self._backend)
        except ReflectionUnavailable as exc:
            self._result.setPlainText(f"Reflections unavailable: {exc}")
            return

        self._reflect_btn.setEnabled(False)
        self._copy_btn.setEnabled(False)
        self._result.setHtml("<i>Reflecting…</i>")

        self._worker = _ReflectionWorker(reflector, ctx)
        self._worker.finished_with.connect(self._on_reflection_done)
        self._worker.failed.connect(self._on_reflection_failed)
        self._worker.start()

    def _on_reflection_done(self, result: Reflection) -> None:
        self._last = result
        self._reflect_btn.setEnabled(True)
        self._render(result)

    def _on_reflection_failed(self, message: str) -> None:
        self._reflect_btn.setEnabled(True)
        self._result.setPlainText(f"Reflection failed: {message}")

    def _on_copy(self) -> None:
        if self._last is None:
            return
        text = self._result.toPlainText()
        QApplication.clipboard().setText(text)

    # ---- rendering -------------------------------------------------------
    def _render(self, r: Reflection) -> None:
        if r.mode == "unavailable":
            self._limited_banner.hide()
            reason = (r.fallback_reason or "unavailable").split(":")[0]
            friendly = {
                "no_context": "Please describe a decision first.",
                "no_values": "Add at least one value in Settings → Ethical "
                "Mirror before reflecting.",
                "no_valid_citations": "The model could not find a clear link "
                "to any of your values on this decision.",
                "prohibited_content": "The model's reply contained content "
                "SHADOW does not allow in reflections.",
                "model_error": "The local model isn't available right now.",
                "empty_model_output": "The model returned an empty reply.",
            }.get(reason, f"Reflection unavailable ({reason}).")
            self._result.setPlainText(friendly)
            self._copy_btn.setEnabled(False)
            return

        if r.mode == "limited":
            self._limited_banner.setText(
                "Limited profile: fewer than 10 values stored. This "
                "reflection is incomplete — add more values in Settings."
            )
            self._limited_banner.show()
        else:
            self._limited_banner.hide()

        lines: list[str] = []
        lines.append("<b>These of your values touch on this:</b>")
        for c in r.citations:
            lines.append(f"&nbsp;&nbsp;• <i>&ldquo;{_escape(c['text'])}&rdquo;</i>")
        if r.tensions:
            lines.append("")
            lines.append("<b>Possible tensions:</b>")
            for t in r.tensions:
                lines.append(f"&nbsp;&nbsp;• {_escape(t)}")
        if r.open_questions:
            lines.append("")
            lines.append("<b>Questions that might clarify:</b>")
            for q in r.open_questions:
                lines.append(f"&nbsp;&nbsp;• {_escape(q)}")
        if r.uncertainty:
            lines.append("")
            lines.append("<b>What I don't know:</b>")
            lines.append(f"&nbsp;&nbsp;{_escape(r.uncertainty)}")
        lines.append("")
        lines.append(
            "<span style='color:#888;font-size:11px'>"
            "This reflection cites only your stated values. It is "
            "advisory — the decision is yours.</span>"
        )
        self._result.setHtml("<br>".join(lines))
        self._copy_btn.setEnabled(True)


def _escape(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
