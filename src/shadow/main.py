import sys

from PySide6.QtWidgets import QApplication

from shadow.config import consent_channels, load_config
from shadow.errors import ErrorReporter, install_exception_hook
from shadow.hal.cpu_backend import CpuBackend
from shadow.memory import CrashRecovery, MemoryStore, RetentionPolicy
from shadow.ui.main_window import MainWindow


def main() -> int:
    import signal

    from PySide6.QtCore import QTimer

    from shadow.perception.uia import _disable_screen_reader_flag

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

    # Startup recovery — detects crashes, repairs orphan observations
    try:
        recovery = CrashRecovery(memory, backend, config)
        rec_summary = recovery.run_startup_recovery()
        if rec_summary.get("shutdown_status") == "unexpected":
            reporter.tray(
                "app",
                "SHADOW recovered from an unexpected shutdown.",
                user_action="Everything looks fine.",
            )
    except Exception as exc:  # noqa: BLE001
        reporter.silent("recovery", f"startup recovery failed: {exc}", exc=exc)

    # Retention pruning — runs at most once per interval
    try:
        policy = RetentionPolicy(memory, config)
        policy.maybe_run()
    except Exception as exc:  # noqa: BLE001
        reporter.silent("retention", f"pruning failed: {exc}", exc=exc)

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

    try:
        result = app.exec()
    finally:
        from shadow.perception.uia import _disable_screen_reader_flag

        _disable_screen_reader_flag()

    return result


if __name__ == "__main__":
    sys.exit(main())
