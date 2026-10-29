"""Tests for C05: Phase 4 task registration.

Verifies the 9 tasks from PRD §22.11 are registered with correct metadata
(group, priority, consent channels, enabled flag, dedup behaviour) and that
the handler-dispatch pattern lets feature commits plug in real implementations.
"""

from __future__ import annotations

import logging
import threading
import time

import pytest

from shadow.agent.p4_tasks import (
    P4_TASK_IDS,
    phase4_task_specs,
    register_p4_handler,
    register_phase4_tasks,
    reset_p4_handlers,
)
from shadow.agent.task_registry import BackgroundTaskRegistry

pytestmark = pytest.mark.p4


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
class FakeConsent:
    def __init__(self, granted=None):
        self.granted = set(granted or ())

    def get_consent(self, ch):
        return ch in self.granted

    def grant(self, ch):
        self.granted.add(ch)

    def revoke(self, ch):
        self.granted.discard(ch)


class FakeConfig:
    def __init__(self, d=None):
        self.d = dict(d or {})

    def get(self, k, default=None):
        return self.d.get(k, default)


class FakeLogger:
    def __init__(self):
        self.warnings = []
        self.infos = []

    def warning(self, msg, extra=None):
        self.warnings.append((msg, extra or {}))

    def info(self, *a, **kw):
        self.infos.append((a, kw))

    def debug(self, *a, **kw): ...

    def error(self, *a, **kw): ...


def make_registry(config=None, consent=None):
    return BackgroundTaskRegistry(
        consent_manager=FakeConsent(consent or set()),
        config=FakeConfig(config or {}),
        logger=FakeLogger(),
    )


@pytest.fixture(autouse=True)
def _reset_handlers():
    reset_p4_handlers()
    yield
    reset_p4_handlers()


# ---------------------------------------------------------------------------
# Registration shape
# ---------------------------------------------------------------------------
def test_all_nine_tasks_registered():
    reg = make_registry()
    added = register_phase4_tasks(reg)
    assert sorted(added) == sorted(P4_TASK_IDS)
    for tid in P4_TASK_IDS:
        assert tid in reg._specs


def test_registration_is_idempotent():
    reg = make_registry()
    register_phase4_tasks(reg)
    added2 = register_phase4_tasks(reg)
    assert added2 == []


def test_nine_task_ids_match_prd():
    """Snapshot: change deliberately if PRD §22.11 changes."""
    assert set(P4_TASK_IDS) == {
        "p4.vision.auto_summary",
        "p4.vision.continuous",
        "p4.digest.daily",
        "p4.digest.weekly",
        "p4.weaver.run",
        "p4.asr.job",
        "p4.notifications.listener",
        "p4.silent_pair.eval",
        "p4.clone.sweep",
    }


# ---------------------------------------------------------------------------
# Metadata wiring
# ---------------------------------------------------------------------------
def test_each_task_has_correct_group_and_flag():
    specs = {s.id: s for s in phase4_task_specs()}
    assert specs["p4.vision.auto_summary"].serialization_group == "vision_bg"
    assert specs["p4.vision.continuous"].serialization_group == "vision_bg"
    assert specs["p4.digest.daily"].serialization_group == "lm_bg"
    assert specs["p4.digest.weekly"].serialization_group == "lm_bg"
    assert specs["p4.weaver.run"].serialization_group == "lm_bg"
    assert specs["p4.asr.job"].serialization_group == "asr"
    assert specs["p4.notifications.listener"].serialization_group == "listener"
    assert specs["p4.silent_pair.eval"].serialization_group == "lm_fg"
    assert specs["p4.clone.sweep"].serialization_group == "maintenance"

    assert specs["p4.vision.auto_summary"].enabled_flag == "auto_summary_enabled"
    assert specs["p4.vision.continuous"].enabled_flag == "continuous_enabled"
    assert specs["p4.digest.daily"].enabled_flag == "digest_schedule_enabled"
    assert specs["p4.digest.weekly"].enabled_flag == "weekly_schedule_enabled"
    assert specs["p4.weaver.run"].enabled_flag == "weaver_enabled"
    assert specs["p4.asr.job"].enabled_flag is None  # user-triggered
    assert specs["p4.notifications.listener"].enabled_flag == "notifications_enabled"
    assert specs["p4.silent_pair.eval"].enabled_flag == "silent_pair_enabled"
    assert specs["p4.clone.sweep"].enabled_flag is None  # maintenance


def test_consent_channels_wired():
    specs = {s.id: s for s in phase4_task_specs()}
    assert set(specs["p4.vision.auto_summary"].consent_channels) == {
        "vision",
        "vision_background",
    }
    assert set(specs["p4.vision.continuous"].consent_channels) == {
        "vision",
        "vision_background",
    }
    assert specs["p4.asr.job"].consent_channels == ["meeting_audio"]
    assert specs["p4.silent_pair.eval"].consent_channels == ["screen_capture"]
    assert specs["p4.notifications.listener"].consent_channels == [
        "notification_summarization",
    ]
    assert specs["p4.clone.sweep"].consent_channels == []


# ---------------------------------------------------------------------------
# Enabled / consent gating
# ---------------------------------------------------------------------------
def test_disabled_task_does_not_invoke_handler():
    calls = []
    register_p4_handler("p4.vision.auto_summary", lambda ctx: calls.append(ctx))
    reg = make_registry(
        config={"auto_summary_enabled": False},
        consent={"vision", "vision_background"},
    )
    register_phase4_tasks(reg)
    reg.tick("p4.vision.auto_summary")
    assert calls == []


def test_enabled_with_consent_invokes_handler():
    calls = []
    register_p4_handler("p4.vision.auto_summary", lambda ctx: calls.append(ctx))
    reg = make_registry(
        config={"auto_summary_enabled": True},
        consent={"vision", "vision_background"},
    )
    register_phase4_tasks(reg)
    reg.tick("p4.vision.auto_summary")
    assert len(calls) == 1


def test_enabled_but_consent_denied_does_not_invoke_handler():
    calls = []
    register_p4_handler("p4.vision.auto_summary", lambda ctx: calls.append(ctx))
    reg = make_registry(
        config={"auto_summary_enabled": True},
        consent={"vision"},  # missing vision_background
    )
    register_phase4_tasks(reg)
    reg.tick("p4.vision.auto_summary")
    assert calls == []


def test_unimplemented_task_logs_info(caplog):
    reg = make_registry(
        config={"auto_summary_enabled": True},
        consent={"vision", "vision_background"},
    )
    register_phase4_tasks(reg)
    with caplog.at_level(logging.INFO, logger="shadow.agent.p4_tasks"):
        reg.tick("p4.vision.auto_summary")
    assert any(
        getattr(r, "task", "") == "p4.vision.auto_summary" for r in caplog.records
    )


def test_register_p4_handler_rejects_unknown_task():
    with pytest.raises(ValueError):
        register_p4_handler("p4.unknown.task", lambda ctx: None)


# ---------------------------------------------------------------------------
# Dedup behaviour
# ---------------------------------------------------------------------------
def test_digest_daily_dedups_by_date():
    calls = []
    register_p4_handler("p4.digest.daily", lambda ctx: calls.append(ctx))
    reg = make_registry(config={"digest_schedule_enabled": True})
    register_phase4_tasks(reg)
    reg.tick("p4.digest.daily", {"date": "2026-10-29"})
    reg.tick("p4.digest.daily", {"date": "2026-10-29"})  # dup — blocked
    reg.tick("p4.digest.daily", {"date": "2026-10-30"})  # new — runs
    assert len(calls) == 2


def test_asr_dedups_by_file_and_meeting():
    calls = []
    register_p4_handler("p4.asr.job", lambda ctx: calls.append(ctx))
    reg = make_registry(consent={"meeting_audio"})
    register_phase4_tasks(reg)
    reg.tick("p4.asr.job", {"file_hash": "abc", "meeting_id": 1})
    reg.tick("p4.asr.job", {"file_hash": "abc", "meeting_id": 1})  # dup
    reg.tick("p4.asr.job", {"file_hash": "abc", "meeting_id": 2})  # new
    reg.tick("p4.asr.job", {"file_hash": "def", "meeting_id": 1})  # new
    assert len(calls) == 3


def test_vision_auto_summary_no_dedup():
    """Interval tasks must run on every tick."""
    calls = []
    register_p4_handler("p4.vision.auto_summary", lambda ctx: calls.append(ctx))
    reg = make_registry(
        config={"auto_summary_enabled": True},
        consent={"vision", "vision_background"},
    )
    register_phase4_tasks(reg)
    for _ in range(3):
        reg.tick("p4.vision.auto_summary")
    assert len(calls) == 3


# ---------------------------------------------------------------------------
# Serialization group in practice
# ---------------------------------------------------------------------------
def test_vision_tasks_serialize_via_group():
    """Both vision tasks share vision_bg; only one runs at a time."""
    started = []

    def slow(ctx):
        started.append(ctx)
        time.sleep(0.1)

    register_p4_handler("p4.vision.auto_summary", slow)
    register_p4_handler("p4.vision.continuous", slow)
    reg = make_registry(
        config={"auto_summary_enabled": True, "continuous_enabled": True},
        consent={"vision", "vision_background"},
    )
    register_phase4_tasks(reg)

    t1 = threading.Thread(target=reg.tick, args=("p4.vision.auto_summary",))
    t1.start()
    time.sleep(0.02)
    reg.tick("p4.vision.continuous")  # blocked — group busy
    t1.join()

    assert len(started) == 1
