import sys

from PySide6.QtWidgets import QApplication

from shadow.config import consent_channels, load_config, vision_config
from shadow.errors import ErrorReporter, install_exception_hook
from shadow.hal import (
    CloudBackend,
    HealthMonitor,
    Moondream2Backend,
    ProviderConfig,
    ProviderPool,
    VisionRouter,
    VisionService,
)
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

    local_backend = CpuBackend(
        model_path=config["model"]["path"],
        n_ctx=config["model"]["n_ctx"],
        n_threads=config["model"].get("n_threads") or None,
        n_gpu_layers=config["model"]["n_gpu_layers"],
        embedder_model=config["model"].get("embedder_model"),
        embedder_tokenizer=config["model"].get("embedder_tokenizer"),
    )

    # Optional cloud layer — falls back to local automatically.
    from shadow.config import build_provider_pool, cloud_enabled
    from shadow.hal import HybridBackend

    backend = local_backend
    if cloud_enabled(config):
        pool = build_provider_pool(config, local_backend=local_backend)
        if pool is not None:
            backend = HybridBackend(
                cloud=pool,
                local=local_backend,
                health=HealthMonitor(),
            )

    # Vision service — lazy loaded, on-demand only.

    vcfg = vision_config(config)

    def _make_vision_backend():
        return Moondream2Backend(
            text_model_path=vcfg["text_model_path"],
            mmproj_path=vcfg["mmproj_path"],
            n_ctx=vcfg["n_ctx"],
            n_threads=vcfg.get("n_threads") or None,
            n_gpu_layers=0,
        )

    vision_service = VisionService(
        _make_vision_backend, enabled=bool(vcfg.get("enabled", True))
    )

    # Dedicated cloud vision pool — separate from the text-model pool.
    from shadow.config import resolve_key

    health = HealthMonitor()
    vision_cloud_pool = None

    vision_cloud_cfg = vcfg.get("cloud") or {}
    text_cloud_cfg = config.get("cloud") or {}

    if vision_cloud_cfg.get("enabled", False):
        # Index the existing provider configuration by provider name.
        configured_providers = {
            str(entry.get("name", "")).lower(): entry
            for entry in text_cloud_cfg.get("providers", [])
            if isinstance(entry, dict)
        }

        vision_providers = []

        # Only attempt providers explicitly selected for vision.
        for priority, provider_name in enumerate(
            vision_cloud_cfg.get("providers", ["gemini"]),
            start=1,
        ):
            entry = configured_providers.get(str(provider_name).lower())

            if not entry or not entry.get("enabled", True):
                print(f"[Main] Provider {provider_name} disabled or not found.")
                continue

            api_key = resolve_key(entry.get("env_key", ""))
            if not api_key:
                print(f"[Main] Provider {provider_name} missing API key.")
                continue

            provider_cfg = ProviderConfig(
                name=entry.get("name", "unknown"),
                base_url=entry.get("base_url", ""),
                model=entry.get("model", ""),
                api_key=api_key,
            )

            candidate = CloudBackend(
                provider=provider_cfg,
                timeout_sec=text_cloud_cfg.get("timeout_sec", 30),
                max_retries=text_cloud_cfg.get("max_retries", 2),
            )

            # Never assume a text-only model supports image input.
            if candidate.supports_vision():
                print(f"[Main] Provider {provider_name} supports vision. Adding to pool.")
                vision_providers.append((priority, candidate))
            else:
                print(f"[Main] Provider {provider_name} (model: {candidate.provider.model}) does NOT support vision.")
                candidate.close()

        if vision_providers:
            vision_cloud_pool = ProviderPool(
                providers=vision_providers,
                local_fallback=None,
            )

    vision_router = VisionRouter(
        local_service=vision_service,
        cloud_pool=vision_cloud_pool,
        config={"cloud": vision_cloud_cfg},
        health=health,
        consent_store=memory,
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

    window = MainWindow(
        backend,
        memory,
        config,
        reporter=reporter,
        vision_service=vision_service,
        vision_router=vision_router,
    )
    window.show()

    try:
        result = app.exec()
    finally:
        from shadow.perception.uia import _disable_screen_reader_flag

        _disable_screen_reader_flag()

    return result


if __name__ == "__main__":
    sys.exit(main())
