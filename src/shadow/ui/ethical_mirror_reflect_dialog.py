"""Ethical Mirror — 'Check against my values' dialog with cloud opt-in (C09b)."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
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

PREVIEW_META_KEY = "ethical_reflection_cloud_preview_shown"


class _ReflectionWorker(QThread):
    finished_with = Signal(object)
    failed = Signal(str)

    def __init__(self, reflector, ctx: str, use_cloud: bool) -> None:
        super().__init__()
        self._reflector = reflector
        self._ctx = ctx
        self._use_cloud = use_cloud

    def run(self) -> None:  # noqa: D401
        try:
            result = self._reflector.reflect(self._ctx, use_cloud=self._use_cloud)
            self.finished_with.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class EthicalMirrorReflectDialog(QDialog):
    def __init__(self, memory, backend, cloud_backend=None, config=None, parent=None):
        super().__init__(parent)
        self._memory = memory
        self._backend = backend
        self._cloud_backend = cloud_backend
        self._config = config
        self._store = EthicalValuesStore(memory)
        self._worker = None
        self._last = None
        self._cloud_provider = "cloud"

        self.setWindowTitle("SHADOW — Check against my values")
        self.resize(700, 620)
        self._build_ui()

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

        # Cloud opt-in row
        cloud_row = QHBoxLayout()
        self._cloud_checkbox = QCheckBox("Use cloud for this reflection", self)
        self._cloud_checkbox.setToolTip(
            "Sends your values + this decision to a configured cloud provider. "
            "Local fallback is available if cloud is unreachable."
        )
        cloud_row.addWidget(self._cloud_checkbox)
        cloud_row.addStretch(1)
        root.addLayout(cloud_row)

        self._cloud_note = QLabel(self)
        self._cloud_note.setWordWrap(True)
        self._cloud_note.setStyleSheet("color: #888; font-size: 11px;")
        root.addWidget(self._cloud_note)
        self._apply_cloud_availability()

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

    # ---- cloud availability --------------------------------------------
    def _cloud_usable(self) -> tuple[bool, str]:
        if self._cloud_backend is None:
            return False, "Cloud chat is not configured."
        from shadow.config import phase4_config

        try:
            p4 = phase4_config(self._config or {})
        except Exception:
            return False, "Phase 4 config unavailable."
        if not p4.get("ethical_mirror_cloud_enabled", False):
            return False, (
                "Enable 'Use cloud for reflections' in Settings → Ethical Mirror."
            )
        try:
            from shadow.agent.ethical_reflection import _cloud_provider_name

            self._cloud_provider = _cloud_provider_name(self._cloud_backend)
        except Exception:
            pass
        return True, ""

    def _apply_cloud_availability(self) -> None:
        usable, reason = self._cloud_usable()
        self._cloud_checkbox.setEnabled(usable)
        if usable:
            self._cloud_checkbox.setChecked(False)  # per-reflection default off
            self._cloud_note.setText(
                f"Cloud: {self._cloud_provider}. "
                "Values + this decision will leave your device if checked."
            )
        else:
            self._cloud_checkbox.setChecked(False)
            self._cloud_note.setText(f"Cloud unavailable — {reason}")

    # ---- preview dialog ------------------------------------------------
    def _show_first_use_preview(self) -> bool:
        if self._memory.get_meta(PREVIEW_META_KEY) == "1":
            return True

        dlg = QDialog(self)
        dlg.setWindowTitle("Send this reflection to cloud?")
        dlg.resize(600, 500)
        layout = QVBoxLayout(dlg)

        intro = QLabel(
            "Your values and this decision will be sent to a third party for "
            "processing. This is a real privacy tradeoff — local reflection "
            "is always available.",
            dlg,
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        layout.addWidget(QLabel("<b>Values that will be sent:</b>", dlg))
        vt = QTextEdit(dlg)
        vt.setReadOnly(True)
        vt.setMaximumHeight(150)
        active = self._store.list_active()
        vt.setPlainText("\n".join(f"• {v['text']}" for v in active))
        layout.addWidget(vt)

        layout.addWidget(QLabel("<b>Decision context that will be sent:</b>", dlg))
        ct = QTextEdit(dlg)
        ct.setReadOnly(True)
        ct.setMaximumHeight(100)
        ct.setPlainText(self._input.toPlainText().strip() or "(empty)")
        layout.addWidget(ct)

        layout.addWidget(
            QLabel(
                f"<b>Destination:</b> {self._cloud_provider}",
                dlg,
            )
        )
        layout.addWidget(
            QLabel(
                "<b>Local fallback:</b> available if cloud is unreachable.",
                dlg,
            )
        )

        dont_ask = QCheckBox("Don't ask again", dlg)
        layout.addWidget(dont_ask)

        buttons = QHBoxLayout()
        local_btn = QPushButton("Use local instead", dlg)
        local_btn.clicked.connect(dlg.reject)
        buttons.addWidget(local_btn)
        buttons.addStretch(1)
        send_btn = QPushButton("Send to cloud", dlg)
        send_btn.setDefault(True)
        send_btn.clicked.connect(dlg.accept)
        buttons.addWidget(send_btn)
        layout.addLayout(buttons)

        accepted = dlg.exec() == QDialog.Accepted
        if accepted and dont_ask.isChecked():
            try:
                self._memory.set_meta(PREVIEW_META_KEY, "1")
            except Exception:
                pass
        return accepted

    # ---- actions -------------------------------------------------------
    def _on_reflect(self) -> None:
        ctx = self._input.toPlainText().strip()
        if not ctx:
            self._result.setHtml("<i>Describe a decision first.</i>")
            return

        use_cloud = False
        if self._cloud_checkbox.isChecked() and self._cloud_checkbox.isEnabled():
            use_cloud = self._show_first_use_preview()

        try:
            reflector = EthicalReflector(
                self._store,
                self._backend,
                cloud_backend=self._cloud_backend,
            )
        except ReflectionUnavailable as exc:
            self._result.setPlainText(f"Reflections unavailable: {exc}")
            return

        self._reflect_btn.setEnabled(False)
        self._copy_btn.setEnabled(False)
        self._result.setHtml("<i>Reflecting…</i>")

        self._worker = _ReflectionWorker(reflector, ctx, use_cloud)
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
        QApplication.clipboard().setText(self._result.toPlainText())

    # ---- rendering -----------------------------------------------------
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

        route_text = {
            "local": "Reflected on device (local model)",
            "cloud": f"Reflected via {self._cloud_provider}",
            "local_fallback": "Cloud unavailable — reflected on device instead",
        }.get(r.route, "")
        if route_text:
            lines.append(
                f"<span style='color:#888;font-size:10px'>Route: {_escape(route_text)}</span>"
            )

        self._result.setHtml("<br>".join(lines))
        self._copy_btn.setEnabled(True)


def _escape(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
