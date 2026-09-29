import sys

from PySide6.QtWidgets import QApplication

from shadow.config import consent_channels, load_config
from shadow.errors import ErrorReporter, install_exception_hook
from shadow.hal.cpu_backend import CpuBackend
from shadow.memory.store import MemoryStore
from shadow.ui.main_window import MainWindow


def main() -> int:
    import signal

    from PySide6.QtCore import QTimer

    config = load_config()

    memory = MemoryStore(
        db_path=config["memory"]["db_path"],
        vector_dim=config["memory"]["vector_dim"],
    )
    memory.seed_consents(consent_channels(config))

    reporter = ErrorReporter(memory=memory)
    install_exception_hook(reporter)

    backend = CpuBackend(
        model_path=config["model"]["path"],
        n_ctx=config["model"]["n_ctx"],
        n_threads=config["model"].get("n_threads") or None,
        n_gpu_layers=config["model"]["n_gpu_layers"],
        embedder_model=config["model"].get("embedder_model"),
        embedder_tokenizer=config["model"].get("embedder_tokenizer"),
    )

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # --- Ctrl+C handling --------------------------------------------------
    # Qt's exec() loop blocks Python signal handling. A 200 ms timer whose
    # callback does nothing gives the interpreter a chance to notice
    # pending SIGINT and raise KeyboardInterrupt.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    _sigint_tick = QTimer()
    _sigint_tick.start(200)
    _sigint_tick.timeout.connect(lambda: None)
    # ----------------------------------------------------------------------

    window = MainWindow(backend, memory, config, reporter=reporter)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
