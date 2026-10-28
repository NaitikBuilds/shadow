"""Phase 4 shared background task registry (G4).

One scheduler for every Phase 4 background task. No feature may create its own
QTimer / threading.Timer / Thread. See docs/design/phase4_task_registry.md.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

TERMINAL_STATES = {"off", "paused", "auto_disabled", "unavailable", "not_running"}


@dataclass
class RetryPolicy:
    max_retries: int = 0
    backoff_ms: int = 0
    pause_after_consecutive_failures: int = 3
    pause_minutes: int = 30


@dataclass
class TaskSpec:
    id: str
    kind: str
    trigger: dict
    dedup_key: Callable[[dict], str] | None = None
    serialization_group: str = "lm_bg"
    priority: int = 5
    cancellable: bool = True
    consent_channels: list[str] = field(default_factory=list)
    enabled_flag: str | None = None
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    handler: Callable[[dict], None] | None = None
    status_probe: Callable[[], dict] | None = None
    cleanup: Callable[[], None] | None = None  # delete ephemeral on revoke/cancel


@dataclass
class _RunState:
    consecutive_failures: int = 0
    paused_until: float | None = None
    last_run: datetime | None = None
    last_error_code: str | None = None
    running: bool = False
    cancel_event: threading.Event = field(default_factory=threading.Event)


class BackgroundTaskRegistry:
    def __init__(self, consent_manager, config, logger):
        self._consent = consent_manager
        self._config = config
        self._log = logger
        self._specs: dict[str, TaskSpec] = {}
        self._state: dict[str, _RunState] = {}
        self._group_locks: dict[str, threading.Lock] = {
            g: threading.Lock()
            for g in ("vision_bg", "lm_bg", "asr", "listener", "lm_fg", "maintenance")
        }
        self._dedup_seen: set[str] = set()
        self._shutdown = threading.Event()
        self._lock = threading.Lock()

    # --- lifecycle ---------------------------------------------------------
    def register(self, spec: TaskSpec) -> None:
        if spec.id in self._specs:
            raise ValueError(f"task {spec.id} already registered")
        if spec.serialization_group not in self._group_locks:
            raise ValueError(f"unknown group {spec.serialization_group}")
        self._specs[spec.id] = spec
        self._state[spec.id] = _RunState()

    def start(self) -> None:
        # dispatch loop scheduled here; hooks into main.py lifecycle
        pass

    def shutdown(self, timeout_sec: float = 5.0) -> None:
        self._shutdown.set()
        deadline = time.time() + timeout_sec
        for st in self._state.values():
            st.cancel_event.set()
        while time.time() < deadline:
            if not any(st.running for st in self._state.values()):
                return
            time.sleep(0.05)
        self._log.warning("shutdown_timeout", extra={"code": "TASK_SHUTDOWN_TIMEOUT"})

    # --- gate --------------------------------------------------------------
    def _consent_ok(self, spec: TaskSpec) -> bool:
        return all(self._consent.get_consent(ch) for ch in spec.consent_channels)

    def _enabled(self, spec: TaskSpec) -> bool:
        if spec.enabled_flag is None:
            return True
        return bool(self._config.get(spec.enabled_flag, False))

    def _paused(self, st: _RunState) -> bool:
        return st.paused_until is not None and time.time() < st.paused_until

    # --- run ---------------------------------------------------------------
    def tick(self, task_id: str, ctx: dict | None = None) -> None:
        ctx = ctx or {}
        spec = self._specs[task_id]
        st = self._state[task_id]
        if self._shutdown.is_set():
            return
        if not self._enabled(spec):
            return
        if not self._consent_ok(spec):
            self._cancel(task_id)
            return
        if self._paused(st):
            return
        key = spec.dedup_key(ctx) if spec.dedup_key else None
        with self._lock:
            if key and key in self._dedup_seen:
                return
            if key:
                self._dedup_seen.add(key)
        group = self._group_locks[spec.serialization_group]
        if not group.acquire(blocking=False):
            return  # another task in this group is running; skip (or queue)
        try:
            st.running = True
            st.cancel_event.clear()
            try:
                spec.handler(ctx)
                st.consecutive_failures = 0
                st.last_run = datetime.now(UTC)
                st.last_error_code = None
            except Exception as exc:  # noqa: BLE001
                st.consecutive_failures += 1
                st.last_error_code = type(exc).__name__
                self._log.warning(
                    "task_failed", extra={"task": task_id, "code": st.last_error_code}
                )
                if (
                    st.consecutive_failures
                    >= spec.retry.pause_after_consecutive_failures
                ):
                    st.paused_until = time.time() + spec.retry.pause_minutes * 60
        finally:
            st.running = False
            group.release()

    def cancel(self, task_id: str) -> None:
        """Public cancel: sets the run's cancel token and invokes cleanup."""
        self._cancel(task_id)

    def _cancel(self, task_id: str) -> None:
        spec = self._specs[task_id]
        st = self._state[task_id]
        st.cancel_event.set()
        if spec.cleanup:
            try:
                spec.cleanup()
            except Exception:  # noqa: BLE001
                self._log.warning("cleanup_failed", extra={"task": task_id})

    # --- status ------------------------------------------------------------
    def status(self, task_id: str) -> dict:
        spec = self._specs[task_id]
        st = self._state[task_id]
        if not self._enabled(spec):
            mode = "Off"
        elif not self._consent_ok(spec):
            mode = "Unavailable"
        elif self._paused(st):
            mode = "Paused"
        elif st.running:
            mode = "Running"
        else:
            mode = "Not running"
        return {
            "id": task_id,
            "mode": mode,
            "running": st.running,
            "last_run": st.last_run.isoformat() if st.last_run else None,
            "last_error_code": st.last_error_code,
        }
