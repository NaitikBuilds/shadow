"""Tests for C08: Ethical Mirror panel + wizard.

Non-Qt logic (resume, skip gating, onboarding state) is exercised as pure
Python; Qt-level tests use pytest-qt's qtbot for smoke construction.
"""

from __future__ import annotations

import pytest

from shadow.agent.ethical_mirror import (
    DISMISS_OFFER_LIMIT,
    ONBOARDING_PROMPTS,
    EthicalValuesStore,
    answered_prompt_count,
    next_unanswered_prompt_index,
)
from shadow.memory import MemoryStore

pytestmark = pytest.mark.p4


@pytest.fixture
def memory(tmp_path):
    s = MemoryStore(str(tmp_path / "test.db"))
    yield s
    s.close()


@pytest.fixture
def store(memory):
    return EthicalValuesStore(memory)


# ---------------------------------------------------------------------------
# Store-level onboarding state
# ---------------------------------------------------------------------------
def test_onboarding_prompts_constant():
    assert len(ONBOARDING_PROMPTS) == 10
    # Non-empty strings
    assert all(isinstance(p, str) and p.strip() for p in ONBOARDING_PROMPTS)


def test_next_unanswered_starts_at_zero(store):
    assert next_unanswered_prompt_index(store) == 0


def test_next_unanswered_skips_answered(store):
    store.add("v0", onboarding_prompt_id=0)
    store.add("v1", onboarding_prompt_id=1)
    assert next_unanswered_prompt_index(store) == 2


def test_next_unanswered_returns_none_when_all_answered(store):
    for i in range(10):
        store.add(f"value {i}", onboarding_prompt_id=i)
    assert next_unanswered_prompt_index(store) is None


def test_answered_prompt_count(store):
    assert answered_prompt_count(store) == 0
    store.add("a", onboarding_prompt_id=0)
    store.add("b", onboarding_prompt_id=2)
    assert answered_prompt_count(store) == 2


def test_is_onboarded_default_false(store):
    assert store.is_onboarded() is False


def test_mark_onboarded(store):
    store.mark_onboarded()
    assert store.is_onboarded() is True


def test_reset_onboarding(store):
    store.mark_onboarded()
    store.increment_dismissed()
    store.reset_onboarding()
    assert store.is_onboarded() is False
    assert store.dismissed_count() == 0


def test_dismiss_counter(store):
    assert store.dismissed_count() == 0
    assert store.increment_dismissed() == 1
    assert store.increment_dismissed() == 2
    assert store.dismissed_count() == 2


def test_opt_out(store):
    assert store.is_opted_out() is False
    store.set_opt_out(True)
    assert store.is_opted_out() is True
    store.set_opt_out(False)
    assert store.is_opted_out() is False


def test_should_offer_on_fresh_start(store):
    assert store.should_offer_onboarding() is True


def test_should_not_offer_when_onboarded(store):
    store.mark_onboarded()
    assert store.should_offer_onboarding() is False


def test_should_not_offer_when_opted_out(store):
    store.set_opt_out(True)
    assert store.should_offer_onboarding() is False


def test_should_stop_offering_after_dismiss_limit(store):
    for _ in range(DISMISS_OFFER_LIMIT):
        store.increment_dismissed()
    assert store.should_offer_onboarding() is False


# ---------------------------------------------------------------------------
# Qt construction smoke tests
# ---------------------------------------------------------------------------
def test_wizard_construction(memory, qtbot):
    from shadow.ui.ethical_mirror_wizard import EthicalMirrorWizard

    wiz = EthicalMirrorWizard(memory)
    qtbot.addWidget(wiz)
    assert wiz.current_step() == 0
    assert wiz.skip_enabled() is False


def test_wizard_skip_enabled_after_three(memory, qtbot):
    store = EthicalValuesStore(memory)
    for i in range(3):
        store.add(f"pre-{i}", onboarding_prompt_id=i)

    from shadow.ui.ethical_mirror_wizard import EthicalMirrorWizard

    wiz = EthicalMirrorWizard(memory)
    qtbot.addWidget(wiz)
    assert wiz.current_step() == 3
    assert wiz.skip_enabled() is True


def test_wizard_completes_when_all_answered(memory, qtbot):
    store = EthicalValuesStore(memory)
    for i in range(10):
        store.add(f"v{i}", onboarding_prompt_id=i)

    from shadow.ui.ethical_mirror_wizard import EthicalMirrorWizard

    wiz = EthicalMirrorWizard(memory)
    qtbot.addWidget(wiz)
    # Constructor auto-completes when all prompts already answered.
    assert wiz.is_completed() is True
    assert store.is_onboarded() is True


def test_panel_construction(memory, qtbot):
    from shadow.ui.ethical_mirror_panel import EthicalMirrorPanel

    panel = EthicalMirrorPanel(memory, config={})
    qtbot.addWidget(panel)
    # No values yet -> limited banner visible.
    assert panel._banner.isVisible() is False  # not shown until widget shown
    # Widget count sanity: tabs are present.
    assert panel._tabs.count() == 2


def test_panel_renders_values(memory, qtbot):
    store = EthicalValuesStore(memory)
    store.add("first value")
    store.add("second value")

    from shadow.ui.ethical_mirror_panel import EthicalMirrorPanel

    panel = EthicalMirrorPanel(memory, config={})
    qtbot.addWidget(panel)
    # Two value rows in the active layout.
    assert panel._active_rows.count() == 2
