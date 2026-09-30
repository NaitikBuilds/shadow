from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_config(path: str = "config.yaml") -> dict:
    config_path = ROOT / path
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def consent_channels(config: dict) -> list[str]:
    """Return the list of consent channel names defined in config."""
    return list(config.get("consent", {}).keys())


def is_consented(config: dict, channel: str) -> bool:
    """Check whether a specific channel is consented in config."""
    return bool(config.get("consent", {}).get(channel, False))


def perception_config(config: dict) -> dict:
    """Return the perception block with safe defaults filled in."""
    defaults = {
        "enabled": True,
        "tick_interval_sec": 30,
        "idle_skip_sec": 120,
        "dedupe_window_sec": 60,
        "ocr_every_n_ticks": 3,
        "sources": {
            "active_window": True,
            "screen_ocr": True,
            "typing_dynamics": True,
            "document_watch": True,
            "calendar": True,
            "clipboard": True,
        },
        "max_title_length": 200,
        "min_title_length": 3,
    }
    user = config.get("perception", {}) or {}
    merged = {**defaults, **user}
    merged["sources"] = {**defaults["sources"], **(user.get("sources") or {})}
    return merged


def source_enabled(config: dict, source_name: str) -> bool:
    """Check whether a perception source is enabled in config."""
    return bool(perception_config(config)["sources"].get(source_name, False))


def tick_interval(config: dict, mode: str | None = None) -> int:
    """Return the effective tick interval for a mode.

    Falls back to the global perception setting if the mode doesn't
    define one. Mode-specific overrides live under modes.<mode>.
    """
    p = perception_config(config)
    if mode:
        mode_cfg = (config.get("modes") or {}).get(mode) or {}
        if "observation_interval_sec" in mode_cfg:
            return int(mode_cfg["observation_interval_sec"])
    return int(p["tick_interval_sec"])


def models_config(config: dict) -> dict:
    """Return the models block with safe defaults filled in."""
    defaults = {
        "cache_dir": "models",
        "verify_on_load": True,
        "auto_download_optional": False,
    }
    return {**defaults, **(config.get("models") or {})}


def retention_config(config: dict) -> dict:
    """Return the retention block with safe defaults filled in."""
    defaults = {
        "observations_days": 0,
        "low_value_days": 7,
        "activity_days": 180,
        "error_logs_days": 30,
        "orphan_observation_hours": 24,
        "prune_interval_hours": 24,
    }
    return {**defaults, **(config.get("retention") or {})}


def budget_config(config: dict) -> dict:
    """Return the perception.budget block with safe defaults."""
    defaults = {
        "enabled": True,
        "active_multiplier": 0.7,
        "idle_multiplier": 1.5,
        "battery_multiplier": 1.5,
        "low_battery_threshold": 20,
        "low_battery_multiplier": 2.0,
        "min_interval_sec": 5,
        "max_interval_sec": 180,
    }
    user = (config.get("perception") or {}).get("budget") or {}
    return {**defaults, **user}


def capture_config(config: dict) -> dict:
    """Return the capture block with safe defaults filled in."""
    defaults = {
        "enabled": True,
        "hotkey": "<ctrl>+<shift>+s",
        "output_dir": "~/SHADOW_workspace/captures",
    }
    return {**defaults, **(config.get("capture") or {})}
