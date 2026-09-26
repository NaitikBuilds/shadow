from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QCloseEvent, QTextCursor
from shadow.ui.indicator import ObservationIndicator
from shadow.ui.privacy_dashboard import PrivacyDashboard
from shadow.ui.consent_panel import ConsentPanel  # NEW in Commit 3
from shadow.memory.retriever import ShadowRetriever
from shadow.perception import ObservationWorker
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,  # NEW in Commit 3
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
import sys


class InferenceWorker(QThread):
    """Runs the LLM in a background thread and emits streamed chunks."""

    chunk = Signal(str)
    done = Signal()
    failed = Signal(str)

    def __init__(self, backend, prompt: str, max_tokens: int):
        super().__init__()
        self.backend = backend
        self.prompt = prompt
        self.max_tokens = max_tokens

    def run(self):
        try:
            for piece in self.backend.generate_stream(
                self.prompt, max_tokens=self.max_tokens
            ):
                if self.isInterruptionRequested():
                    break
                self.chunk.emit(piece)
            self.done.emit()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self, backend, memory, config):
        super().__init__()
        self.backend = backend
        self.memory = memory
        self.config = config
        self.retriever = ShadowRetriever(self.memory, self.backend)
        self.worker = None
        self._shutting_down = False

        self.setWindowTitle("SHADOW — Silent On-Device Life Context Agent")
        self.resize(900, 600)

        central = QWidget()
        layout = QVBoxLayout(central)

        info = backend.info
        self.backend_label = QLabel(
            f"Backend: {info['backend'].upper()}  •  threads: {info.get('threads', '?')}"
        )
        layout.addWidget(self.backend_label)

        self.indicator = ObservationIndicator(self.memory, self.config)
        layout.addWidget(self.indicator)

        self.observer_status = QLabel("Observer: not started")
        self.observer_status.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.observer_status)

        self.observer = None

        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Mode:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["lite", "balanced", "active"])
        self.mode_combo.setCurrentText(config["modes"]["default"])
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output)

        input_layout = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Ask your Shadow…")
        self.input.returnPressed.connect(self.send_query)
        input_layout.addWidget(self.input)
        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self.send_query)
        input_layout.addWidget(self.send_btn)
        layout.addLayout(input_layout)

        self.wipe_btn = QPushButton("Wipe Shadow")
        self.wipe_btn.clicked.connect(self.wipe_shadow)
        layout.addWidget(self.wipe_btn)

        self.setCentralWidget(central)
        self._build_menu()  # NEW in Commit 3
        self.memory.log_activity("app_start", "SHADOW started")

        self._start_observer()

    # ---------- menu (NEW in Commit 3) ----------

    def _build_menu(self):
        menu = self.menuBar()
        settings_menu = menu.addMenu("Settings")

        consent_action = settings_menu.addAction("Consent…")
        consent_action.triggered.connect(self.open_consent_panel)

        privacy_action = settings_menu.addAction("Privacy Dashboard…")
        privacy_action.triggered.connect(self.open_privacy_dashboard)

    def open_consent_panel(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("SHADOW — Consent")
        dlg.resize(560, 640)
        layout = QVBoxLayout(dlg)

        panel = ConsentPanel(self.memory, self.config)
        panel.consent_changed.connect(self._on_consent_changed)
        layout.addWidget(panel)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn)

        dlg.exec()

    def open_privacy_dashboard(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("SHADOW — Privacy Dashboard")
        dlg.resize(640, 520)
        layout = QVBoxLayout(dlg)

        dash = PrivacyDashboard(self.memory, self.backend)
        layout.addWidget(dash)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn)

        dlg.exec()

    def _on_consent_changed(self, channel: str, enabled: bool):
        self.memory.log_activity(
            "consent_change", f"{channel}={'on' if enabled else 'off'}"
        )
        self.indicator.refresh()

    def _on_mode_changed(self, mode: str):
        if self.observer is not None:
            self.observer.set_mode(mode)
        self.memory.log_activity("mode_change", mode)

    # ---------- observer lifecycle ----------

    def _start_observer(self):
        from shadow.config import perception_config

        pcfg = perception_config(self.config)
        if not pcfg.get("enabled", True):
            self.observer_status.setText("Observer: disabled in config")
            return
        self.observer = ObservationWorker(self.memory, self.backend, self.config)
        self.observer.tick.connect(self._on_observer_tick)
        self.observer.observation.connect(self._on_observer_observation)
        self.observer.skipped.connect(self._on_observer_skipped)
        self.observer.error.connect(self._on_observer_error)
        self.observer.start()
        self.observer_status.setText("Observer: starting…")
        self.memory.log_activity("observer_start", "observer loop started")

    def _on_observer_tick(self, count: int):
        self.observer_status.setText(f"Observer: tick {count}")

    def _on_observer_observation(self, source: str, preview: str):
        self.observer_status.setText(f"Observer: recorded from {source}")
        self.memory.log_activity("observation", f"{source}: {preview[:80]}")

    def _on_observer_skipped(self, reason: str, detail: str):
        self.observer_status.setText(f"Observer: skipped ({reason})")

    def _on_observer_error(self, message: str):
        self.observer_status.setText(f"Observer error: {message[:80]}")
        self.memory.log_activity("observer_error", message[:120])

    # ---------- query flow ----------

    def send_query(self):
        try:
            self._send_query_inner()
        except Exception:
            import traceback

            tb = traceback.format_exc()
            print(tb, file=sys.stderr)
            self.output.append(f"<b style='color:red'>Exception:</b><pre>{tb}</pre>")

    def _send_query_inner(self):
        if self._shutting_down:
            return
        if self.worker is not None and self.worker.isRunning():
            return
        prompt = self.input.text().strip()
        if not prompt:
            return
        self.input.clear()

        augmented = self._build_prompt_with_context(prompt)

        self.output.append(f"<b>You:</b> {prompt}")
        self.output.append("<b>Shadow:</b> ")

        mode = self.mode_combo.currentText()
        max_tokens = self.config["modes"][mode]["model_max_tokens"]

        self.worker = InferenceWorker(self.backend, augmented, max_tokens)
        self.worker.chunk.connect(self.on_chunk)
        self.worker.done.connect(self.on_done)
        self.worker.failed.connect(self.on_error)
        self.worker.start()

    def on_chunk(self, text: str):
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.output.setTextCursor(cursor)
        self.output.ensureCursorVisible()

    def on_done(self):
        if self._shutting_down:
            return
        self.output.append("")
        self.memory.log_activity("query", "completed")

    def on_error(self, message: str):
        if self._shutting_down:
            return
        self.output.append(f"<b style='color:red'>Error:</b> {message}")
        self.memory.log_activity("error", message[:120])

    def wipe_shadow(self):
        self.memory.wipe()
        self.output.append("<b>Shadow:</b> All local memory wiped.")
        self.memory.log_activity("wipe", "Full Shadow wipe executed")

    def _build_prompt_with_context(self, user_prompt: str) -> str:
        # 1) Always try semantic retrieval.
        context = self.retriever.context_for(user_prompt, k=5)

        # 2) Also check for temporal keywords.
        for window in ("last month", "yesterday", "last week", "today"):
            if window in user_prompt.lower():
                temporal = self.retriever.temporal(window)
                if temporal:
                    lines = "\n".join(
                        f"- [{o['timestamp']}] {o['content'][:150]}"
                        for o in temporal[:5]
                    )
                    context = (context + "\n\n" if context else "") + (
                        f"Observations from {window}:\n{lines}"
                    )
                break

        if not context:
            return user_prompt
        return (
            "You are answering using the user's own past observations. "
            "Use them if relevant; ignore them if not.\n\n"
            f"{context}\n\nUser question: {user_prompt}"
        )

    # ---------- graceful shutdown ----------

    def closeEvent(self, event: QCloseEvent):
        self._shutting_down = True

        if self.observer is not None and self.observer.isRunning():
            self.observer.stop()
            if not self.observer.wait(3000):
                print("[shadow] observer did not stop within 3 s")

        worker = self.worker
        if worker is not None and worker.isRunning():
            worker.requestInterruption()
            if not worker.wait(3000):
                print("[shadow] worker did not stop within 3 s; forcing exit")

        try:
            self.memory.log_activity("app_stop", "SHADOW closed")
        finally:
            self.memory.close()

        event.accept()
