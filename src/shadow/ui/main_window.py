from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QCloseEvent, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,                # NEW in Commit 3
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from shadow.ui.consent_panel import ConsentPanel   # NEW in Commit 3


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

        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Mode:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["lite", "balanced", "active"])
        self.mode_combo.setCurrentText(config["modes"]["default"])
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)

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
        self._build_menu()                                    # NEW in Commit 3
        self.memory.log_activity("app_start", "SHADOW started")

    # ---------- menu (NEW in Commit 3) ----------

    def _build_menu(self):
        menu = self.menuBar()
        settings_menu = menu.addMenu("Settings")

        consent_action = settings_menu.addAction("Consent…")
        consent_action.triggered.connect(self.open_consent_panel)

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

    def _on_consent_changed(self, channel: str, enabled: bool):
        self.memory.log_activity(
            "consent_change", f"{channel}={'on' if enabled else 'off'}"
        )

    # ---------- query flow ----------

    def send_query(self):
        if self._shutting_down:
            return
        if self.worker is not None and self.worker.isRunning():
            return
        prompt = self.input.text().strip()
        if not prompt:
            return
        self.input.clear()

        self.output.append(f"<b>You:</b> {prompt}")
        self.output.append("<b>Shadow:</b> ")

        mode = self.mode_combo.currentText()
        max_tokens = self.config["modes"][mode]["model_max_tokens"]

        self.worker = InferenceWorker(self.backend, prompt, max_tokens)
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

    # ---------- graceful shutdown ----------

    def closeEvent(self, event: QCloseEvent):
        self._shutting_down = True

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