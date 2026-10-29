import logging
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

log = logging.getLogger(__name__)


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
            "screen_uia": True,
            "typing_dynamics": True,
            "document_watch": True,
            "image_files": True,
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


def redaction_config(config: dict) -> dict:
    """Return the redaction block with safe defaults."""
    defaults = {
        "enabled": True,
        "redact_emails": False,
        "placeholder": "[REDACTED]",
    }
    return {**defaults, **(config.get("redaction") or {})}


def uia_config(config: dict) -> dict:
    """Return the perception.uia block with safe defaults."""
    defaults = {
        "enabled": True,
        "max_depth": 8,
        "max_elements": 500,
        "min_useful_nodes": 3,
    }
    user = (config.get("perception") or {}).get("uia") or {}
    return {**defaults, **user}


def window_classifier_config(config: dict) -> dict:
    """Return the window_classifier block with safe defaults."""
    defaults = {"custom_map": {}}
    user = (config.get("perception") or {}).get("window_classifier") or {}
    return {**defaults, **user}


def interactive_config(config: dict) -> dict:
    """Return the perception.interactive block with safe defaults."""
    defaults = {"max_elements": 100}
    user = (config.get("perception") or {}).get("interactive") or {}
    return {**defaults, **user}


def identifiers_config(config: dict) -> dict:
    """Return the perception.identifiers block with safe defaults."""
    defaults = {"extract_urls": True, "extract_paths": True}
    user = (config.get("perception") or {}).get("identifiers") or {}
    return {**defaults, **user}


def tabs_config(config: dict) -> dict:
    """Return the perception.tabs block with safe defaults."""
    defaults = {
        "enabled": True,
        "stale_hours": 6,
        "retention_days": 7,
        "related_min_overlap": 2,
    }
    user = (config.get("perception") or {}).get("tabs") or {}
    return {**defaults, **user}


def change_detection_config(config: dict) -> dict:
    """Return the perception.change_detection block with safe defaults."""
    defaults = {
        "enabled": True,
        "threshold": 5,
        "hash_size": 8,
        "min_interval_ms": 500,
    }
    user = (config.get("perception") or {}).get("change_detection") or {}
    return {**defaults, **user}


def cadence_config(config: dict) -> dict:
    """Return the perception.cadence block with safe defaults."""
    defaults = {
        "enabled": True,
        "min_interval_sec": 5,
        "max_interval_sec": 60,
        "idle_interval_sec": 30,
        "accelerate_multiplier": 0.5,
        "backoff_multiplier": 1.5,
    }
    user = (config.get("perception") or {}).get("cadence") or {}
    return {**defaults, **user}


def reading_position_config(config: dict) -> dict:
    """Return the perception.reading_position block with safe defaults."""
    defaults = {
        "enabled": True,
        "min_change_pct": 5,
        "retention_days": 30,
    }
    user = (config.get("perception") or {}).get("reading_position") or {}
    return {**defaults, **user}


def stuck_config(config: dict) -> dict:
    """Return the agent.stuck block with safe defaults."""
    defaults = {
        "enabled": True,
        "static_minutes": 20,
        "alternation_minutes": 15,
        "alternation_count": 8,
        "error_lookback_minutes": 5,
    }
    user = (config.get("agent") or {}).get("stuck") or {}
    return {**defaults, **user}


def cloud_config(config: dict) -> dict:
    """Return the cloud block with safe defaults filled in.

    Provider entries are deep-merged with the default provider list
    so partial overrides don't remove default providers.
    """
    defaults = {
        "enabled": False,
        "fallback_to_local": True,
        "timeout_sec": 30,
        "max_retries": 2,
        "log_prompts": False,
        "providers": [],
    }
    user = config.get("cloud") or {}
    merged = {**defaults, **user}

    # If the user provided a providers list, use it verbatim.
    # If not, no providers are configured.
    providers = user.get("providers")
    if isinstance(providers, list):
        merged["providers"] = providers
    else:
        merged["providers"] = []

    return merged


def cloud_enabled(config: dict) -> bool:
    """Return True if cloud LLM is enabled in config."""
    return bool(cloud_config(config).get("enabled", False))


def resolve_key(env_key: str) -> str:
    """Resolve an API key from env var, then Windows Credential Manager.

    Returns empty string if not found. Never raises.
    """
    if not env_key:
        return ""

    import os

    value = os.environ.get(env_key, "").strip()
    if value:
        return value

    # Try Windows Credential Manager via keyring
    try:
        import keyring

        value = keyring.get_password("SHADOW", env_key)
        if value:
            return value.strip()
    except Exception:
        pass

    return ""


def build_provider_pool(config: dict, local_backend=None):
    """Construct a ProviderPool from config.

    Returns None if cloud is disabled or no providers have keys.

    Import is local to avoid a circular dependency: config.py must
    stay importable without hal/ imports at module load time.
    """
    if not cloud_enabled(config):
        return None

    from shadow.hal.cloud_backend import CloudBackend, ProviderConfig
    from shadow.hal.provider_pool import ProviderPool

    cfg = cloud_config(config)
    providers = []

    for entry in cfg.get("providers") or []:
        if not entry.get("enabled", True):
            continue
        env_key = entry.get("env_key", "")
        api_key = resolve_key(env_key)
        if not api_key:
            continue
        provider_cfg = ProviderConfig(
            name=entry.get("name", "unknown"),
            base_url=entry.get("base_url", ""),
            model=entry.get("model", ""),
            api_key=api_key,
        )
        backend = CloudBackend(
            provider=provider_cfg,
            timeout_sec=cfg.get("timeout_sec", 30),
            max_retries=cfg.get("max_retries", 2),
        )
        providers.append((entry.get("priority", 99), backend))

    if not providers:
        return None

    fallback = local_backend if cfg.get("fallback_to_local") else None
    return ProviderPool(providers=providers, local_fallback=fallback)


def set_cloud_key(env_key: str, value: str) -> bool:
    """Store an API key in Windows Credential Manager.

    Returns True on success, False otherwise.
    """
    try:
        import keyring

        keyring.set_password("SHADOW", env_key, value)
        return True
    except Exception:
        return False


def delete_cloud_key(env_key: str) -> bool:
    """Remove an API key from Windows Credential Manager."""
    try:
        import keyring

        keyring.delete_password("SHADOW", env_key)
        return True
    except Exception:
        return False


def save_cloud_settings(
    config_path: str, enabled: bool, fallback_to_local: bool
) -> bool:
    """Persist the cloud.enabled and cloud.fallback_to_local flags to YAML.

    Preserves all other config sections and provider entries. Returns
    True on success.
    """
    try:
        import yaml

        path = ROOT / config_path
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        cloud = data.setdefault("cloud", {})
        cloud["enabled"] = bool(enabled)
        cloud["fallback_to_local"] = bool(fallback_to_local)

        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
        return True
    except Exception:
        return False


def vision_config(config: dict) -> dict:
    """Return vision configuration with safe nested defaults."""

    defaults = {
        "enabled": True,
        "text_model_path": ("models/moondream2/moondream2-text-model-f16.gguf"),
        "mmproj_path": ("models/moondream2/moondream2-mmproj-f16.gguf"),
        "n_threads": 4,
        "n_ctx": 2048,
        "unload_after_sec": 300,
        "prompt_cooldown_min": 15,
        "require_thin_text": True,
        "image_max_side": 1024,
        "image_max_bytes": 10 * 1024 * 1024,
        "local_fallback": True,
        "cloud": {
            "enabled": False,
            "providers": ["gemini"],
            "require_preview": True,
            "fallback_to_local": True,
        },
    }

    user = config.get("vision") or {}
    merged = {**defaults, **user}

    # Deep-merge this nested section so partial YAML overrides do not
    # erase the safe defaults.
    merged["cloud"] = {
        **defaults["cloud"],
        **(user.get("cloud") or {}),
    }

    return merged


def image_files_config(config: dict) -> dict:
    """Return the perception.image_files block with safe defaults."""
    defaults = {
        "watch_folders": ["~/Pictures", "~/Documents", "~/Downloads"],
        "extensions": [".png", ".jpg", ".jpeg", ".webp"],
        "max_file_size_mb": 15,
        "image_max_side": 1024,
    }
    user = (config.get("perception") or {}).get("image_files") or {}
    return {**defaults, **user}


def region_capture_config(config: dict) -> dict:
    """Return region-capture configuration with safe defaults."""
    defaults = {
        "enabled": False,
        "hotkey": "<ctrl>+<shift>+q",
        "default_prompt": "What is this?",
        "max_region_mb": 10,
    }
    user = (config.get("vision") or {}).get("region_capture") or {}
    return {**defaults, **user}


def reconcile_retention_config(cfg: dict) -> dict:
    """One-time fix for the audit's 90 vs 0 mismatch.

    If `observation.retention_days` exists and `retention.observations_days` is
    missing or 0, copy the legacy value over and log a deprecation notice.
    Does NOT retroactively delete existing data; the new setting applies on the
    next prune cycle.
    """
    legacy = (cfg.get("observation") or {}).get("retention_days")
    retention = cfg.setdefault("retention", {})
    current = retention.get("observations_days")

    if legacy is not None and (current is None or int(current) == 0):
        retention["observations_days"] = int(legacy)
        log.warning(
            "config_deprecated",
            extra={
                "code": "CFG_RETENTION_DEPRECATED",
                "key": "observation.retention_days",
                "value": legacy,
                "action": "copied to retention.observations_days",
            },
        )

    return cfg


# ---------------------------------------------------------------------------
# Phase 4 config (C04)
# ---------------------------------------------------------------------------
# Every key required by PRD §22.15. Defaults match the PRD; background /
# audio / vision / notification / cloud features MUST default off
# (FR-P4-SEC-13). Invalid values fall back to the default and log a
# CFG_P4_INVALID notice naming the offending key.

_PHASE4_DEFAULTS: dict = {
    # Background vision (DR-P4-07/08)
    "auto_summary_enabled": False,
    "continuous_enabled": False,
    "continuous_cadence_min": 5,
    "continuous_max_inferences_per_hour": 30,
    "continuous_idle_autodisable_hours": 8,
    "bg_vision_model_preference": "auto",
    # Ethical Mirror (DR-P4-03)
    "ethical_mirror_opt_out": False,
    # Shadow Cloning (DR-P4-10)
    "clone_max_concurrent": 2,
    "clone_idle_expiry_min": 240,
    # Cross-Project Weaver
    "weaver_enabled": False,
    "weaver_included_projects": [],
    "weaver_excluded_projects": [],
    "weaver_min_confidence": 0.6,
    "weaver_max_candidates_per_run": 20,
    "weaver_state_days": 90,
    # Silent Pair Partner
    "silent_pair_enabled": False,
    "silent_pair_min_confidence": 0.7,
    "silent_pair_max_per_hour": 4,
    "silent_pair_cooldown_min": 15,
    # Meeting ASR (DR-P4-04)
    "asr_model_id": "whisper-tiny.en",
    "asr_max_file_mb": 500,
    "asr_max_duration_min": 180,
    # Meeting Prep
    "meeting_prep_lookahead_hours": 24,
    "meeting_prep_auto": False,
    # Digest / Weekly (DR-P4-05/13)
    "digest_schedule_enabled": False,
    "digest_schedule_time": "18:00",
    "digest_day_rollover": "00:00",
    "weekly_start_day": "monday",
    "weekly_schedule_enabled": False,
    # Notification Summarization (DR-P4-09)
    "notifications_enabled": False,
    "notifications_allowed": [],
    "notifications_denied": [],
    "notifications_summary_max_per_hour": 4,
    "notifications_retention_days": 7,
    # Timeline / Entity Browser
    "timeline_page_size": 100,
    "entity_page_size": 100,
    "entity_stale_days": 180,
}

_PHASE4_BOOL_KEYS = frozenset(
    {
        "auto_summary_enabled",
        "continuous_enabled",
        "ethical_mirror_opt_out",
        "weaver_enabled",
        "silent_pair_enabled",
        "meeting_prep_auto",
        "digest_schedule_enabled",
        "weekly_schedule_enabled",
        "notifications_enabled",
    }
)

_PHASE4_INT_RANGES: dict = {
    "continuous_cadence_min": (1, 5),
    "continuous_max_inferences_per_hour": (1, 30),
    "continuous_idle_autodisable_hours": (1, 8),
    "clone_max_concurrent": (1, 5),
    "clone_idle_expiry_min": (15, 1440),
    "weaver_max_candidates_per_run": (5, 50),
    "weaver_state_days": (30, 365),
    "silent_pair_max_per_hour": (1, 12),
    "silent_pair_cooldown_min": (5, 120),
    "asr_max_file_mb": (10, 2000),
    "asr_max_duration_min": (5, 600),
    "meeting_prep_lookahead_hours": (1, 168),
    "notifications_summary_max_per_hour": (1, 12),
    "notifications_retention_days": (1, 90),
    "timeline_page_size": (25, 500),
    "entity_page_size": (25, 500),
    "entity_stale_days": (30, 720),
}

_PHASE4_FLOAT_RANGES: dict = {
    "weaver_min_confidence": (0.3, 0.95),
    "silent_pair_min_confidence": (0.5, 0.95),
}

_PHASE4_ENUMS: dict = {
    "bg_vision_model_preference": {"auto", "florence2", "moondream2"},
    "weekly_start_day": {
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    },
}

_PHASE4_TIME_KEYS = frozenset({"digest_schedule_time", "digest_day_rollover"})

_PHASE4_LIST_KEYS = frozenset(
    {
        "weaver_included_projects",
        "weaver_excluded_projects",
        "notifications_allowed",
        "notifications_denied",
    }
)


def _warn_p4_invalid(key: str, raw, reason: str) -> None:
    log.warning(
        "config_invalid",
        extra={
            "code": "CFG_P4_INVALID",
            "key": key,
            "raw": repr(raw),
            "reason": reason,
        },
    )


def _validate_phase4_value(key: str, raw, default):
    """Coerce `raw` to the type of `default`. On any error, log
    CFG_P4_INVALID and return the default."""
    try:
        if key in _PHASE4_BOOL_KEYS:
            if isinstance(raw, bool):
                return raw
            if isinstance(raw, int) and raw in (0, 1):
                return bool(raw)
            if isinstance(raw, str):
                v = raw.strip().lower()
                if v in ("true", "1", "yes", "on"):
                    return True
                if v in ("false", "0", "no", "off"):
                    return False
            raise ValueError(f"not a boolean: {raw!r}")

        if key in _PHASE4_INT_RANGES:
            lo, hi = _PHASE4_INT_RANGES[key]
            v = int(raw)
            if key == "continuous_cadence_min" and v not in (1, 3, 5):
                raise ValueError(f"cadence must be 1/3/5, got {v}")
            if not (lo <= v <= hi):
                raise ValueError(f"{v} outside [{lo}, {hi}]")
            return v

        if key in _PHASE4_FLOAT_RANGES:
            lo, hi = _PHASE4_FLOAT_RANGES[key]
            v = float(raw)
            if not (lo <= v <= hi):
                raise ValueError(f"{v} outside [{lo}, {hi}]")
            return v

        if key in _PHASE4_ENUMS:
            v = str(raw).strip().lower()
            if v not in _PHASE4_ENUMS[key]:
                raise ValueError(f"{v!r} not in {_PHASE4_ENUMS[key]}")
            return v

        if key in _PHASE4_TIME_KEYS:
            v = str(raw).strip()
            parts = v.split(":")
            if len(parts) != 2:
                raise ValueError(f"expected HH:MM, got {v!r}")
            h, m = int(parts[0]), int(parts[1])
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError(f"time out of range: {v!r}")
            return f"{h:02d}:{m:02d}"

        if key in _PHASE4_LIST_KEYS:
            if not isinstance(raw, list):
                raise ValueError(f"expected list, got {type(raw).__name__}")
            return [str(x) for x in raw]

        if isinstance(default, str):
            return str(raw)
        return raw
    except (TypeError, ValueError) as exc:
        _warn_p4_invalid(key, raw, str(exc))
        return list(default) if isinstance(default, list) else default


def phase4_config(config: dict) -> dict:
    """Return the Phase 4 config section with defaults filled in and
    invalid values replaced by safe defaults.

    All booleans default to False for background / audio / vision /
    notification / cloud features (FR-P4-SEC-13). Invalid values fall
    back to the default and log a CFG_P4_INVALID notice with the key.
    """
    raw_section = config.get("phase4") or {}
    if not isinstance(raw_section, dict):
        _warn_p4_invalid(
            "phase4", raw_section, "top-level phase4 section must be a dict"
        )
        raw_section = {}

    out: dict = {}
    for key, default in _PHASE4_DEFAULTS.items():
        if key not in raw_section:
            out[key] = list(default) if isinstance(default, list) else default
            continue
        out[key] = _validate_phase4_value(key, raw_section[key], default)
    return out
