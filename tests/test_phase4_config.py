"""Tests for C04: Phase 4 config registry (§22.15).

Covers FR-P4-SEC-13:
  - All 37 keys present with the exact defaults from §22.15.
  - Every boolean for a background / audio / vision / notification /
    cloud feature defaults to False.
  - Invalid values fall back to the default with a CFG_P4_INVALID
    notice that names the offending key.
  - Ranges, enums, list and HH:MM validation are enforced.
  - A malformed phase4 section (non-dict) is tolerated.
"""

from __future__ import annotations

import logging

import pytest

from shadow.config import _PHASE4_DEFAULTS, phase4_config

pytestmark = pytest.mark.p4


# Keys whose boolean default MUST be False (FR-P4-SEC-13).
_BOOL_KEYS_MUST_DEFAULT_OFF = (
    "auto_summary_enabled",
    "continuous_enabled",
    "ethical_mirror_opt_out",
    "weaver_enabled",
    "silent_pair_enabled",
    "meeting_prep_auto",
    "digest_schedule_enabled",
    "weekly_schedule_enabled",
    "notifications_enabled",
)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
def test_defaults_when_section_absent():
    out = phase4_config({})
    for key, expected in _PHASE4_DEFAULTS.items():
        assert out[key] == expected, f"{key} default mismatch"


def test_all_bool_keys_default_false():
    out = phase4_config({})
    for key in _BOOL_KEYS_MUST_DEFAULT_OFF:
        assert out[key] is False, f"{key} must default False (FR-P4-SEC-13)"


def test_defaults_match_prd_snapshot():
    """Locked snapshot of the exact §22.15 defaults. Update deliberately."""
    out = phase4_config({})
    assert out["continuous_cadence_min"] == 5
    assert out["continuous_max_inferences_per_hour"] == 30
    assert out["continuous_idle_autodisable_hours"] == 8
    assert out["bg_vision_model_preference"] == "auto"
    assert out["clone_max_concurrent"] == 2
    assert out["weaver_min_confidence"] == 0.6
    assert out["silent_pair_max_per_hour"] == 4
    assert out["asr_max_file_mb"] == 500
    assert out["digest_schedule_time"] == "18:00"
    assert out["weekly_start_day"] == "monday"
    assert out["notifications_retention_days"] == 7
    assert out["timeline_page_size"] == 100


def test_lists_are_deep_copied():
    """Mutating the returned list must not corrupt _PHASE4_DEFAULTS."""
    out = phase4_config({})
    out["weaver_included_projects"].append("p1")
    out2 = phase4_config({})
    assert out2["weaver_included_projects"] == []


# ---------------------------------------------------------------------------
# Valid values preserved
# ---------------------------------------------------------------------------
def test_valid_overrides_preserved():
    cfg = {
        "phase4": {
            "auto_summary_enabled": True,
            "continuous_cadence_min": 3,
            "weaver_min_confidence": 0.8,
            "weaver_included_projects": ["p1", "p2"],
            "digest_schedule_time": "09:30",
            "weekly_start_day": "sunday",
        }
    }
    out = phase4_config(cfg)
    assert out["auto_summary_enabled"] is True
    assert out["continuous_cadence_min"] == 3
    assert out["weaver_min_confidence"] == 0.8
    assert out["weaver_included_projects"] == ["p1", "p2"]
    assert out["digest_schedule_time"] == "09:30"
    assert out["weekly_start_day"] == "sunday"


def test_bool_accepts_common_string_and_int_forms():
    for raw, expected in [
        ("true", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        (1, True),
        ("false", False),
        ("0", False),
        ("no", False),
        ("off", False),
        (0, False),
    ]:
        out = phase4_config({"phase4": {"auto_summary_enabled": raw}})
        assert out["auto_summary_enabled"] is expected, f"raw={raw!r}"


# ---------------------------------------------------------------------------
# Invalid values fall back
# ---------------------------------------------------------------------------
def _has_cfg_p4_invalid(caplog, key=None):
    for rec in caplog.records:
        if getattr(rec, "code", None) == "CFG_P4_INVALID":
            if key is None or getattr(rec, "key", None) == key:
                return True
    return False


def test_invalid_bool_falls_back(caplog):
    with caplog.at_level(logging.WARNING):
        out = phase4_config({"phase4": {"auto_summary_enabled": "banana"}})
    assert out["auto_summary_enabled"] is False
    assert _has_cfg_p4_invalid(caplog, "auto_summary_enabled")


def test_invalid_int_out_of_range_falls_back(caplog):
    with caplog.at_level(logging.WARNING):
        out = phase4_config({"phase4": {"clone_max_concurrent": 99}})
    assert out["clone_max_concurrent"] == 2
    assert _has_cfg_p4_invalid(caplog, "clone_max_concurrent")


def test_invalid_cadence_2_falls_back(caplog):
    with caplog.at_level(logging.WARNING):
        out = phase4_config({"phase4": {"continuous_cadence_min": 2}})
    assert out["continuous_cadence_min"] == 5
    assert _has_cfg_p4_invalid(caplog, "continuous_cadence_min")


@pytest.mark.parametrize("cadence", [1, 3, 5])
def test_valid_cadence_accepted(cadence):
    out = phase4_config({"phase4": {"continuous_cadence_min": cadence}})
    assert out["continuous_cadence_min"] == cadence


def test_invalid_confidence_falls_back(caplog):
    with caplog.at_level(logging.WARNING):
        out = phase4_config({"phase4": {"weaver_min_confidence": 1.5}})
    assert out["weaver_min_confidence"] == 0.6
    assert _has_cfg_p4_invalid(caplog, "weaver_min_confidence")


def test_invalid_enum_falls_back(caplog):
    with caplog.at_level(logging.WARNING):
        out = phase4_config({"phase4": {"weekly_start_day": "funday"}})
    assert out["weekly_start_day"] == "monday"
    assert _has_cfg_p4_invalid(caplog, "weekly_start_day")


def test_invalid_time_format_falls_back(caplog):
    with caplog.at_level(logging.WARNING):
        out = phase4_config({"phase4": {"digest_schedule_time": "25:99"}})
    assert out["digest_schedule_time"] == "18:00"
    assert _has_cfg_p4_invalid(caplog, "digest_schedule_time")


def test_invalid_list_type_falls_back(caplog):
    with caplog.at_level(logging.WARNING):
        out = phase4_config({"phase4": {"weaver_included_projects": "p1"}})
    assert out["weaver_included_projects"] == []
    assert _has_cfg_p4_invalid(caplog, "weaver_included_projects")


def test_section_not_a_dict_falls_back(caplog):
    with caplog.at_level(logging.WARNING):
        out = phase4_config({"phase4": "oops"})
    # Whole section defaults; every key present.
    for key, expected in _PHASE4_DEFAULTS.items():
        assert out[key] == expected
    assert _has_cfg_p4_invalid(caplog, "phase4")


def test_partial_section_fills_missing_keys():
    out = phase4_config({"phase4": {"auto_summary_enabled": True}})
    assert out["auto_summary_enabled"] is True
    # Everything else defaulted.
    for key, expected in _PHASE4_DEFAULTS.items():
        if key == "auto_summary_enabled":
            continue
        assert out[key] == expected, f"{key} should default"
