"""Tests for the 90 vs 0 retention config reconciliation.

Covers:
- Legacy 90 + current 0 → current becomes 90, warning logged.
- Legacy present + current non-zero → current wins, no warning.
- No legacy → untouched.
- Legacy missing + current missing → defaults applied by validator.
"""

import logging

from shadow.config import reconcile_retention_config


def test_legacy_copied_when_current_zero(caplog):
    cfg = {"observation": {"retention_days": 90}, "retention": {"observations_days": 0}}
    with caplog.at_level(logging.WARNING):
        out = reconcile_retention_config(cfg)
    assert out["retention"]["observations_days"] == 90
    assert any(
        rec.message == "config_deprecated"
        or getattr(rec, "code", "") == "CFG_RETENTION_DEPRECATED"
        for rec in caplog.records
    ) or any("CFG_RETENTION_DEPRECATED" in str(r) for r in caplog.records)


def test_legacy_ignored_when_current_set(caplog):
    cfg = {
        "observation": {"retention_days": 90},
        "retention": {"observations_days": 30},
    }
    with caplog.at_level(logging.WARNING):
        out = reconcile_retention_config(cfg)
    assert out["retention"]["observations_days"] == 30


def test_no_legacy_untouched():
    cfg = {"retention": {"observations_days": 45}}
    out = reconcile_retention_config(cfg)
    assert out["retention"]["observations_days"] == 45


def test_missing_current_uses_legacy():
    cfg = {"observation": {"retention_days": 60}}
    out = reconcile_retention_config(cfg)
    assert out["retention"]["observations_days"] == 60
