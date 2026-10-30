"""Tests for C05b: bootstrap_phase4 wires registry + consent channels into main.

Verifies:
  - bootstrap creates the registry, registers 9 specs, sets the singleton.
  - Idempotent: second call returns the same registry.
  - vision_background consent channel is seeded to False in memory.
  - Notification channel not registered without DR-P4-09 approval.
  - get_active_registry reflects the bootstrap (and reset clears it).
  - The registry uses the FLATTENED phase4 dict (so TaskSpec.enabled_flag
    lookups work).
  - Shutdown via registry.shutdown() blocks future ticks.
"""

from __future__ import annotations

import pytest

from shadow.agent.p4_tasks import (
    P4_TASK_IDS,
    bootstrap_phase4,
    get_active_registry,
    reset_active_registry,
    set_active_registry,
)
from shadow.memory import MemoryStore

pytestmark = pytest.mark.p4


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_active_registry()
    yield
    reset_active_registry()


@pytest.fixture
def memory(tmp_path):
    s = MemoryStore(str(tmp_path / "test.db"))
    yield s
    s.close()


def _base_config():
    """Minimal config matching the shape phase4_config expects."""
    return {"phase4": {}}


# ---------------------------------------------------------------------------
# Bootstrap behaviour
# ---------------------------------------------------------------------------
def test_bootstrap_creates_and_sets_registry(memory):
    reg = bootstrap_phase4(memory, _base_config())
    assert reg is not None
    assert get_active_registry() is reg
    for tid in P4_TASK_IDS:
        assert tid in reg._specs


def test_bootstrap_idempotent(memory):
    reg1 = bootstrap_phase4(memory, _base_config())
    reg2 = bootstrap_phase4(memory, _base_config())
    assert reg1 is reg2


def test_bootstrap_registers_vision_background_channel(memory):
    bootstrap_phase4(memory, _base_config())
    # Default should be False (fail-closed)
    assert memory.get_consent("vision_background") is False


def test_bootstrap_skips_notification_channel_without_dr_p4_09(memory):
    bootstrap_phase4(memory, _base_config())
    # Not registered by default
    try:
        existing = memory.get_consent("notification_summarization")
    except Exception:
        existing = None
    assert existing in (None, False)


def test_bootstrap_uses_flattened_config_for_enabled_flags(memory):
    """TaskSpec.enabled_flag lookups must work — requires flat phase4 dict."""
    cfg = {"phase4": {"auto_summary_enabled": True}}
    reg = bootstrap_phase4(memory, cfg)
    # The registry's config must be the flattened dict, so .get returns True.
    assert reg._config.get("auto_summary_enabled") is True


def test_bootstrap_handles_missing_phase4_section(memory):
    """Empty config → all defaults applied."""
    reg = bootstrap_phase4(memory, {})
    assert reg._config.get("auto_summary_enabled") is False
    assert reg._config.get("continuous_enabled") is False


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
def test_set_and_get_active_registry(memory):
    reg = bootstrap_phase4(memory, _base_config())
    assert get_active_registry() is reg
    reset_active_registry()
    assert get_active_registry() is None


def test_set_active_registry_directly(memory):
    from shadow.agent.task_registry import BackgroundTaskRegistry

    reg = BackgroundTaskRegistry(
        consent_manager=memory,
        config={},
        logger=None,
    )
    set_active_registry(reg)
    assert get_active_registry() is reg


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------
def test_shutdown_after_bootstrap_blocks_ticks(memory):
    reg = bootstrap_phase4(memory, _base_config())
    reg.shutdown(timeout_sec=1.0)
    calls = []
    from shadow.agent.p4_tasks import register_p4_handler

    register_p4_handler("p4.clone.sweep", lambda ctx: calls.append(1))
    reg.tick("p4.clone.sweep")
    assert calls == []


# ---------------------------------------------------------------------------
# Edge: bootstrap with bad config
# ---------------------------------------------------------------------------
def test_bootstrap_tolerates_non_dict_phase4(memory):
    """phase4_config handles a non-dict section; bootstrap should too."""
    reg = bootstrap_phase4(memory, {"phase4": "oops"})
    # Registry still created; defaults applied.
    assert reg._config.get("auto_summary_enabled") is False
