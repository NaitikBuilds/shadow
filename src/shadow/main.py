import sys

from PySide6.QtWidgets import QApplication

from shadow.config import load_config, consent_channels   # NEW
from shadow.hal.cpu_backend import CpuBackend
from shadow.memory.store import MemoryStore
from shadow.ui.main_window import MainWindow


def main() -> int:
    config = load_config()

    backend = CpuBackend(
    model_path=config["model"]["path"],
    n_ctx=config["model"]["n_ctx"],
    n_threads=config["model"].get("n_threads") or None,
    n_gpu_layers=config["model"]["n_gpu_layers"],
    embedder_model=config["model"].get("embedder_model"),
    embedder_tokenizer=config["model"].get("embedder_tokenizer"),
    )

    memory = MemoryStore(
        db_path=config["memory"]["db_path"],
        vector_dim=config["memory"]["vector_dim"],
    )
    memory.seed_consents(consent_channels(config))   # NEW

    app = QApplication(sys.argv)
    window = MainWindow(backend, memory, config)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())