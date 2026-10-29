"""Tests for C03: ConsentGate + Phase 4 channel registration.

Covers FR-P4-SEC-04 / FR-P4-SEC-05:
  - Gate present / absent / revoked / errored behaviour.
  - Existing seed_consents behaviour unchanged.
  - notification_summarization not registered without DR-P4-09 approval.
"""

from __future__ import annotations

import pytest

from shadow.agent.consent_gate import (
    CHANNEL_NOTIFICATION_SUMMARIZATION,
    CHANNEL_VISION_BACKGROUND,
    DR_P4_09_APPROVED_KEY,
    ConsentDenied,
    ConsentGate,
    register_phase4_consent_channels,
)
from shadow.memory import MemoryStore

pytestmark = pytest.mark.p4


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------
class _MissingRaises:
    def get_consent(self, channel):
        raise RuntimeError("store offline")


class _DictStore:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def get_consent(self, channel):
        return self.values.get(channel)


class _ConfigDict:
    def __init__(self, d=None):
        self.d = d or {}

    def get(self, key, default=None):
        return self.d.get(key, default)


@pytest.fixture
def temp_db(tmp_path):
    return str(tmp_path / "test.db")


BASELINE_CHANNELS = (
    "screen_capture",
    "typing_dynamics",
    "document_parsing",
    "calendar",
    "clipboard",
    "vision",
    "vision_cloud",
    "meeting_audio",
    "dictation",
    "mcp_local",
    "voice_interrupt",
    "cloud_connectors",
)


@pytest.fixture
def store(temp_db):
    s = MemoryStore(temp_db)
    s.seed_consents(list(BASELINE_CHANNELS))
    yield s
    s.close()


# ---------------------------------------------------------------------------
# Gate behaviour
# ---------------------------------------------------------------------------
def test_check_denies_when_channel_missing():
    assert ConsentGate(store=_DictStore({})).check("vision_background") is False


def test_check_denies_when_explicitly_denied():
    gate = ConsentGate(store=_DictStore({"vision_background": False}))
    assert gate.check("vision_background") is False


def test_check_allows_when_granted():
    gate = ConsentGate(store=_DictStore({"vision_background": True}))
    assert gate.check("vision_background") is True


def test_check_denies_on_store_exception():
    assert ConsentGate(store=_MissingRaises()).check("vision_background") is False


def test_check_denies_on_empty_channel_name():
    gate = ConsentGate(store=_DictStore({"": True}))
    assert gate.check("") is False


def test_require_raises_when_denied():
    gate = ConsentGate(store=_DictStore({}))
    with pytest.raises(ConsentDenied) as exc:
        gate.require("vision_background")
    assert exc.value.channel == "vision_background"


def test_require_passes_when_granted():
    ConsentGate(store=_DictStore({"vision_background": True})).require(
        "vision_background"
    )


def test_all_granted_requires_every_channel():
    gate = ConsentGate(
        store=_DictStore(
            {
                "vision_background": True,
                "meeting_audio": False,
            }
        )
    )
    assert gate.all_granted(["vision_background"]) is True
    assert gate.all_granted(["vision_background", "meeting_audio"]) is False


def test_all_granted_empty_list_is_false():
    assert ConsentGate(store=_DictStore({})).all_granted([]) is False


def test_any_denied_returns_first_missing():
    gate = ConsentGate(store=_DictStore({"a": True, "c": True}))
    assert gate.any_denied(["a", "b", "c"]) == "b"
    assert gate.any_denied(["a", "c"]) is None


# ---------------------------------------------------------------------------
# Registration against real MemoryStore
# ---------------------------------------------------------------------------
def test_register_adds_vision_background_default_false(store):
    added = register_phase4_consent_channels(store)
    assert CHANNEL_VISION_BACKGROUND in added
    assert store.get_consent(CHANNEL_VISION_BACKGROUND) is False


def test_register_is_idempotent(store):
    first = register_phase4_consent_channels(store)
    second = register_phase4_consent_channels(store)
    assert CHANNEL_VISION_BACKGROUND in first
    assert CHANNEL_VISION_BACKGROUND not in second


def test_register_does_not_overwrite_existing_grant(store):
    store.ensure_consent(CHANNEL_VISION_BACKGROUND, granted=False)
    store.set_consent(CHANNEL_VISION_BACKGROUND, True)
    register_phase4_consent_channels(store)
    assert store.get_consent(CHANNEL_VISION_BACKGROUND) is True


def test_register_skips_notifications_when_unapproved(store):
    added = register_phase4_consent_channels(store)
    assert CHANNEL_NOTIFICATION_SUMMARIZATION not in added
    try:
        existing = store.get_consent(CHANNEL_NOTIFICATION_SUMMARIZATION)
    except Exception:
        existing = None
    assert existing in (None, False)


def test_register_adds_notifications_when_approved(store):
    cfg = _ConfigDict({DR_P4_09_APPROVED_KEY: True})
    added = register_phase4_consent_channels(store, config=cfg)
    assert CHANNEL_NOTIFICATION_SUMMARIZATION in added
    assert store.get_consent(CHANNEL_NOTIFICATION_SUMMARIZATION) is False


def test_existing_channels_unchanged_by_registration(store):
    baseline = {
        "screen_capture": store.get_consent("screen_capture"),
        "vision": store.get_consent("vision"),
        "vision_cloud": store.get_consent("vision_cloud"),
        "meeting_audio": store.get_consent("meeting_audio"),
    }
    register_phase4_consent_channels(store)
    for ch, val in baseline.items():
        assert store.get_consent(ch) == val, f"channel {ch} unexpectedly changed"


# ---------------------------------------------------------------------------
# End-to-end: gate + real store
# ---------------------------------------------------------------------------
def test_gate_live_state_through_registration_and_revoke(store):
    register_phase4_consent_channels(store)
    gate = ConsentGate(store=store)

    assert gate.check(CHANNEL_VISION_BACKGROUND) is False

    store.set_consent(CHANNEL_VISION_BACKGROUND, True)
    assert gate.check(CHANNEL_VISION_BACKGROUND) is True

    store.set_consent(CHANNEL_VISION_BACKGROUND, False)
    assert gate.check(CHANNEL_VISION_BACKGROUND) is False
