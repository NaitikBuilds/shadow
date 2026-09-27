from shadow.config import (
    load_config,
    perception_config,
    source_enabled,
    tick_interval,
)


def test_perception_block_present():
    cfg = load_config()
    p = perception_config(cfg)
    assert p["enabled"] is True
    assert p["tick_interval_sec"] > 0
    assert p["ocr_every_n_ticks"] >= 0


def test_defaults_when_block_missing():
    p = perception_config({})
    assert p["enabled"] is True
    assert p["tick_interval_sec"] == 30
    assert p["sources"]["active_window"] is True
    assert p["sources"]["typing_dynamics"] is True


def test_partial_sources_override_keeps_defaults():
    cfg = {"perception": {"sources": {"typing_dynamics": True}}}
    p = perception_config(cfg)
    assert p["sources"]["typing_dynamics"] is True
    assert p["sources"]["active_window"] is True  # default preserved


def test_source_enabled_helper():
    cfg = load_config()
    # Every source shipped in this build should be available.
    # Consent — not this flag — is what gates actual observation.
    for source in ("active_window", "screen_ocr", "typing_dynamics"):
        assert source_enabled(cfg, source) is True
    # Unknown sources default to disabled.
    assert source_enabled(cfg, "nonexistent_source") is False


def test_tick_interval_respects_modes():
    cfg = load_config()
    # modes.lite.observation_interval_sec = 60 in Phase 1 config
    assert tick_interval(cfg, "lite") == 60
    assert tick_interval(cfg, "balanced") == 30
    assert tick_interval(cfg, "active") == 10


def test_tick_interval_falls_back_without_mode():
    cfg = load_config()
    assert tick_interval(cfg) == cfg["perception"]["tick_interval_sec"]
