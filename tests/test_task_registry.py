"""Tests for G4: Phase 4 shared BackgroundTaskRegistry.

Covers PRD §22.11 / §22.12.4 and exit gates G9 (task cancellation and
shutdown verified):

  - Registration: duplicate ids and unknown groups are rejected
  - Disabled tasks make zero handler calls; status mode is "Off"
  - Consent denied fails closed; status mode is "Unavailable"
  - Enabled + granted runs the handler and sets last_run
  - Dedup key prevents repeat runs; different keys run each
  - Serialization groups are mutually exclusive; different groups concurrent
  - Cancel sets cancel_event, runs cleanup, and stops a cooperative
    handler within NFR-P4-05's 2 s budget
  - Consent revocation cancels + runs cleanup on the next tick
  - Shutdown completes within 5 s and blocks future ticks
  - Retry policy pauses after N consecutive failures
  - Status reflects live state (config + consent + paused), not config alone

Some tests touch `reg._state[...]` directly — acceptable for a skeleton
whose `_RunState` is not yet public API.
"""

from __future__ import annotations

import threading
import time

import pytest

from shadow.agent.task_registry import (
    BackgroundTaskRegistry,
    RetryPolicy,
    TaskSpec,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
class FakeConsent:
    def __init__(self) -> None:
        self.granted: set[str] = set()

    def grant(self, channel: str) -> None:
        self.granted.add(channel)

    def revoke(self, channel: str) -> None:
        self.granted.discard(channel)

    def get_consent(self, channel: str) -> bool:
        return channel in self.granted


class FakeConfig:
    def __init__(self, values: dict | None = None) -> None:
        self.values = values or {}

    def get(self, key: str, default=None):
        return self.values.get(key, default)


class FakeLogger:
    def __init__(self) -> None:
        self.warnings: list[tuple[str, dict]] = []

    def warning(self, msg: str, extra: dict | None = None) -> None:
        self.warnings.append((msg, extra or {}))

    def info(self, *a, **kw) -> None: ...
    def debug(self, *a, **kw) -> None: ...
    def error(self, *a, **kw) -> None: ...


def _make(
    consent: FakeConsent | None = None, config: FakeConfig | None = None
) -> BackgroundTaskRegistry:
    return BackgroundTaskRegistry(
        consent_manager=consent or FakeConsent(),
        config=config or FakeConfig(),
        logger=FakeLogger(),
    )


def _simple_spec(**overrides) -> TaskSpec:
    base = dict(
        id="test.task",
        kind="interval",
        trigger={"interval_sec": 60},
        serialization_group="lm_bg",
        handler=lambda ctx: None,
    )
    base.update(overrides)
    return TaskSpec(**base)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
def test_register_rejects_duplicate_id():
    reg = _make()
    reg.register(_simple_spec(id="dup"))
    with pytest.raises(ValueError):
        reg.register(_simple_spec(id="dup"))


def test_register_rejects_unknown_group():
    reg = _make()
    with pytest.raises(ValueError):
        reg.register(_simple_spec(id="bad", serialization_group="not_a_group"))


# ---------------------------------------------------------------------------
# Disabled / consent gating
# ---------------------------------------------------------------------------
def test_disabled_task_makes_zero_handler_calls():
    calls: list[int] = []
    cfg = FakeConfig({"auto_summary_enabled": False})
    reg = _make(config=cfg)
    reg.register(
        _simple_spec(
            id="vis",
            enabled_flag="auto_summary_enabled",
            handler=lambda ctx: calls.append(1),
        )
    )
    for _ in range(5):
        reg.tick("vis")
    assert calls == []
    assert reg.status("vis")["mode"] == "Off"


def test_consent_denied_fails_closed():
    calls: list[int] = []
    consent = FakeConsent()  # nothing granted
    reg = _make(consent=consent)
    reg.register(
        _simple_spec(
            id="asr",
            consent_channels=["meeting_audio"],
            handler=lambda ctx: calls.append(1),
        )
    )
    reg.tick("asr")
    assert calls == []
    assert reg.status("asr")["mode"] == "Unavailable"


def test_enabled_and_granted_runs_handler():
    calls: list[int] = []
    consent = FakeConsent()
    consent.grant("meeting_audio")
    cfg = FakeConfig({"asr_enabled": True})
    reg = _make(consent=consent, config=cfg)
    reg.register(
        _simple_spec(
            id="asr",
            enabled_flag="asr_enabled",
            consent_channels=["meeting_audio"],
            handler=lambda ctx: calls.append(1),
        )
    )
    reg.tick("asr")
    assert calls == [1]
    assert reg.status("asr")["last_run"] is not None


# ---------------------------------------------------------------------------
# Dedup
# ---------------------------------------------------------------------------
def test_dedup_same_key_runs_once():
    calls: list[int] = []
    reg = _make()
    reg.register(
        _simple_spec(
            id="d",
            dedup_key=lambda ctx: "k1",
            handler=lambda ctx: calls.append(1),
        )
    )
    reg.tick("d")
    reg.tick("d")
    reg.tick("d")
    assert calls == [1]


def test_dedup_different_keys_run_each():
    calls: list[str] = []
    reg = _make()
    reg.register(
        _simple_spec(
            id="d",
            dedup_key=lambda ctx: ctx.get("k"),
            handler=lambda ctx: calls.append(ctx.get("k")),
        )
    )
    reg.tick("d", {"k": "a"})
    reg.tick("d", {"k": "b"})
    reg.tick("d", {"k": "a"})  # duplicate of first -> suppressed
    assert calls == ["a", "b"]


# ---------------------------------------------------------------------------
# Serialization groups
# ---------------------------------------------------------------------------
def test_serialization_group_is_exclusive():
    """Two tasks in the same group: only one runs at a time."""
    started = threading.Event()
    results: list[str] = []
    lock = threading.Lock()

    def slow(who: str) -> None:
        started.set()
        time.sleep(0.2)
        with lock:
            results.append(who)

    reg = _make()
    reg.register(
        _simple_spec(
            id="a",
            serialization_group="vision_bg",
            handler=lambda ctx: slow("a"),
        )
    )
    reg.register(
        _simple_spec(
            id="b",
            serialization_group="vision_bg",
            handler=lambda ctx: slow("b"),
        )
    )

    t1 = threading.Thread(target=reg.tick, args=("a",))
    t1.start()
    assert started.wait(timeout=1.0), "task a never started"
    t2 = threading.Thread(target=reg.tick, args=("b",))
    t2.start()
    t1.join()
    t2.join()

    assert results == ["a"], f"expected only 'a' to run, got {results}"


def test_different_groups_can_run_concurrently():
    a_started = threading.Event()
    b_ran: list[int] = []
    release_a = threading.Event()

    def handler_a(ctx):
        a_started.set()
        release_a.wait(timeout=1.0)

    reg = _make()
    reg.register(_simple_spec(id="a", serialization_group="lm_bg", handler=handler_a))
    reg.register(
        _simple_spec(
            id="b",
            serialization_group="maintenance",
            handler=lambda ctx: b_ran.append(1),
        )
    )

    t = threading.Thread(target=reg.tick, args=("a",))
    t.start()
    assert a_started.wait(timeout=1.0)
    reg.tick("b")  # different group — should not be blocked
    assert b_ran == [1]
    release_a.set()
    t.join()


# ---------------------------------------------------------------------------
# Cancellation & cleanup
# ---------------------------------------------------------------------------
def test_cancel_sets_flag_and_runs_cleanup():
    cleaned: list[int] = []
    reg = _make()
    reg.register(
        _simple_spec(
            id="c",
            handler=lambda ctx: None,
            cleanup=lambda: cleaned.append(1),
        )
    )
    reg.tick("c")
    reg.cancel("c")
    assert reg._state["c"].cancel_event.is_set()
    assert cleaned == [1]


def test_consent_revocation_cancels_and_cleans_up():
    cleanup_calls: list[int] = []
    consent = FakeConsent()
    consent.grant("meeting_audio")
    reg = _make(consent=consent)
    reg.register(
        _simple_spec(
            id="asr",
            consent_channels=["meeting_audio"],
            handler=lambda ctx: None,
            cleanup=lambda: cleanup_calls.append(1),
        )
    )
    reg.tick("asr")  # baseline: runs fine
    consent.revoke("meeting_audio")
    reg.tick("asr")  # tick sees consent denied -> cancel -> cleanup
    assert cleanup_calls == [1]
    assert reg._state["asr"].cancel_event.is_set()


def test_cancel_terminates_in_flight_handler_within_2s():
    """A cooperative handler must stop within NFR-P4-05's 2 s budget."""
    stopped_at: list[float] = []
    cancel_observed = threading.Event()

    def cooperative(ctx):
        st = reg._state["coop"]
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if st.cancel_event.is_set():
                stopped_at.append(time.time())
                cancel_observed.set()
                return
            time.sleep(0.02)

    reg = _make()
    reg.register(_simple_spec(id="coop", handler=cooperative))

    t = threading.Thread(target=reg.tick, args=("coop",))
    t.start()
    time.sleep(0.05)
    start = time.time()
    reg.cancel("coop")
    assert cancel_observed.wait(timeout=2.0), "handler did not observe cancel in 2 s"
    elapsed = stopped_at[0] - start
    assert elapsed < 2.0, f"cancel took {elapsed:.2f}s (>2s)"
    t.join()


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------
def test_shutdown_completes_within_5s():
    reg = _make()
    reg.register(
        _simple_spec(
            id="a",
            handler=lambda ctx: time.sleep(0.1),
        )
    )
    t = threading.Thread(target=reg.tick, args=("a",))
    t.start()
    time.sleep(0.02)
    start = time.time()
    reg.shutdown(timeout_sec=5.0)
    elapsed = time.time() - start
    t.join()
    assert elapsed < 5.0, f"shutdown took {elapsed:.2f}s (>5s)"


def test_shutdown_blocks_future_ticks():
    calls: list[int] = []
    reg = _make()
    reg.register(_simple_spec(id="a", handler=lambda ctx: calls.append(1)))
    reg.shutdown(timeout_sec=1.0)
    reg.tick("a")  # must not run
    assert calls == []


# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------
def test_pause_after_consecutive_failures():
    def always_fail(ctx):
        raise RuntimeError("boom")

    reg = _make()
    reg.register(
        _simple_spec(
            id="f",
            handler=always_fail,
            retry=RetryPolicy(pause_after_consecutive_failures=3, pause_minutes=30),
        )
    )

    reg.tick("f")  # 1
    reg.tick("f")  # 2
    reg.tick("f")  # 3 -> pause
    assert reg._state["f"].consecutive_failures == 3
    assert reg._state["f"].paused_until is not None
    assert reg.status("f")["mode"] == "Paused"


def test_pause_does_not_break_success_path():
    calls: list[int] = []
    reg = _make()
    reg.register(
        _simple_spec(
            id="ok",
            handler=lambda ctx: calls.append(1),
            retry=RetryPolicy(pause_after_consecutive_failures=3),
        )
    )
    reg.tick("ok")
    reg.tick("ok")
    assert calls == [1, 1]
    assert reg._state["ok"].consecutive_failures == 0
    assert reg._state["ok"].paused_until is None


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
def test_status_reflects_live_state_not_config():
    cfg = FakeConfig({"x_enabled": True})
    consent = FakeConsent()
    reg = _make(config=cfg, consent=consent)
    reg.register(
        _simple_spec(
            id="s",
            enabled_flag="x_enabled",
            consent_channels=["vision"],
            handler=lambda ctx: None,
        )
    )
    # Enabled but consent denied -> Unavailable
    assert reg.status("s")["mode"] == "Unavailable"
    # Grant consent -> Not running
    consent.grant("vision")
    assert reg.status("s")["mode"] == "Not running"
    # Turn off config -> Off
    cfg.values["x_enabled"] = False
    assert reg.status("s")["mode"] == "Off"
