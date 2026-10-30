"""Phase 4 task registration (C05).

Registers the 9 background tasks from PRD §22.11 with the shared
BackgroundTaskRegistry. Feature commits replace each stub handler with
a real implementation via register_p4_handler(task_id, handler).

Design:
  - register_phase4_tasks(registry)   — idempotent; called once at startup
  - register_p4_handler(task_id, h)   — features call this in their commits
  - phase4_task_specs()               — inspectable list of canonical specs
  - reset_p4_handlers()               — test-only helper

The registry's `config` must be the FLATTENED Phase 4 dict (from
`phase4_config(load_config())`), not the nested `{"phase4": {...}}` shape,
because TaskSpec.enabled_flag reads keys directly.

No scheduler lives here. The registry's tick() is driven externally.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from shadow.config import phase4_config

from .consent_gate import register_phase4_consent_channels
from .task_registry import BackgroundTaskRegistry, RetryPolicy, TaskSpec

_p4_log = logging.getLogger(__name__)
_P4_HANDLERS: dict[str, Callable[[dict], None]] = {}


P4_TASK_IDS: tuple[str, ...] = (
    "p4.vision.auto_summary",
    "p4.vision.continuous",
    "p4.digest.daily",
    "p4.digest.weekly",
    "p4.weaver.run",
    "p4.asr.job",
    "p4.notifications.listener",
    "p4.silent_pair.eval",
    "p4.clone.sweep",
)


def register_p4_handler(task_id: str, handler: Callable[[dict], None]) -> None:
    """Feature commits register their real handler here.

    Overwrites any previously-registered handler for the same task id.
    """
    if task_id not in P4_TASK_IDS:
        raise ValueError(f"unknown Phase 4 task id: {task_id}")
    _P4_HANDLERS[task_id] = handler
    _p4_log.info("p4_handler_registered", extra={"task": task_id})


def reset_p4_handlers() -> None:
    """Test-only: clear all registered handler implementations."""
    _P4_HANDLERS.clear()


def _stub_dispatch(ctx: dict, task_id: str) -> None:
    impl = _P4_HANDLERS.get(task_id)
    if impl is None:
        _p4_log.info("p4_task_handler_not_implemented", extra={"task": task_id})
        return
    impl(ctx)


def _handler_for(task_id: str) -> Callable[[dict], None]:
    def _h(ctx: dict) -> None:
        _stub_dispatch(ctx, task_id)

    _h.__name__ = f"p4_handler_{task_id.replace('.', '_')}"
    return _h


def _build_spec(task_id: str) -> TaskSpec:
    common = dict(
        id=task_id,
        kind="background",
        handler=_handler_for(task_id),
    )

    if task_id == "p4.vision.auto_summary":
        return TaskSpec(
            **common,
            trigger={"kind": "interval", "interval_sec": 600},
            serialization_group="vision_bg",
            priority=7,
            consent_channels=["vision", "vision_background"],
            enabled_flag="auto_summary_enabled",
            retry=RetryPolicy(
                max_retries=1,
                pause_after_consecutive_failures=3,
                pause_minutes=30,
            ),
            dedup_key=None,  # interval task — runs every tick
        )
    if task_id == "p4.vision.continuous":
        return TaskSpec(
            **common,
            trigger={
                "kind": "interval_config",
                "key": "continuous_cadence_min",
                "unit": "min",
            },
            serialization_group="vision_bg",
            priority=7,
            consent_channels=["vision", "vision_background"],
            enabled_flag="continuous_enabled",
            retry=RetryPolicy(
                max_retries=1,
                pause_after_consecutive_failures=3,
                pause_minutes=30,
            ),
            dedup_key=None,
        )
    if task_id == "p4.digest.daily":
        return TaskSpec(
            **common,
            trigger={"kind": "schedule", "freq": "daily"},
            serialization_group="lm_bg",
            priority=7,
            consent_channels=[],
            enabled_flag="digest_schedule_enabled",
            dedup_key=lambda ctx: (f"digest:daily:{ctx.get('date') or 'today'}"),
        )
    if task_id == "p4.digest.weekly":
        return TaskSpec(
            **common,
            trigger={"kind": "schedule", "freq": "weekly"},
            serialization_group="lm_bg",
            priority=7,
            consent_channels=[],
            enabled_flag="weekly_schedule_enabled",
            dedup_key=lambda ctx: (f"digest:weekly:{ctx.get('week') or 'this'}"),
        )
    if task_id == "p4.weaver.run":
        return TaskSpec(
            **common,
            trigger={"kind": "manual_or_schedule"},
            serialization_group="lm_bg",
            priority=7,
            consent_channels=[],
            enabled_flag="weaver_enabled",
            dedup_key=None,  # user-triggered; group lock prevents concurrency
        )
    if task_id == "p4.asr.job":
        return TaskSpec(
            **common,
            trigger={"kind": "manual"},
            serialization_group="asr",
            priority=5,
            consent_channels=["meeting_audio"],
            enabled_flag=None,
            dedup_key=lambda ctx: (
                f"asr:{ctx.get('file_hash', '')}:{ctx.get('meeting_id', '')}"
            ),
        )
    if task_id == "p4.notifications.listener":
        return TaskSpec(
            **common,
            trigger={"kind": "event", "source": "os_notification"},
            serialization_group="listener",
            priority=7,
            consent_channels=["notification_summarization"],
            enabled_flag="notifications_enabled",
            dedup_key=None,  # one listener, many events
        )
    if task_id == "p4.silent_pair.eval":
        return TaskSpec(
            **common,
            trigger={"kind": "event", "source": "context_change"},
            serialization_group="lm_fg",
            priority=5,
            consent_channels=["screen_capture"],
            enabled_flag="silent_pair_enabled",
            dedup_key=None,
        )
    if task_id == "p4.clone.sweep":
        return TaskSpec(
            **common,
            trigger={"kind": "startup_and_interval", "interval_sec": 3600},
            serialization_group="maintenance",
            priority=7,
            consent_channels=[],
            enabled_flag=None,
            dedup_key=None,
        )

    raise ValueError(f"unknown Phase 4 task id: {task_id}")


def phase4_task_specs() -> list[TaskSpec]:
    """Return the canonical list of Phase 4 TaskSpecs (fresh objects each call)."""
    return [_build_spec(tid) for tid in P4_TASK_IDS]


def register_phase4_tasks(registry: BackgroundTaskRegistry) -> list[str]:
    """Register all Phase 4 tasks with the given registry. Idempotent.

    Returns the list of task ids newly registered this call.
    """
    added: list[str] = []
    for spec in phase4_task_specs():
        try:
            registry.register(spec)
            added.append(spec.id)
        except ValueError:
            continue
    _p4_log.info(
        "p4_tasks_registered",
        extra={"count": len(added), "total": len(P4_TASK_IDS)},
    )
    return added


# ---------------------------------------------------------------------------
# Active-registry singleton + bootstrap (C05b)
# ---------------------------------------------------------------------------
_active_registry: BackgroundTaskRegistry | None = None
_active_registry_lock = threading.Lock()


def set_active_registry(registry: BackgroundTaskRegistry) -> None:
    """Expose the process-wide registry that feature modules register against."""
    global _active_registry
    with _active_registry_lock:
        _active_registry = registry


def get_active_registry() -> BackgroundTaskRegistry | None:
    """Return the process-wide registry, or None if bootstrap hasn't run."""
    with _active_registry_lock:
        return _active_registry


def reset_active_registry() -> None:
    """Test-only helper: clear the singleton."""
    global _active_registry
    with _active_registry_lock:
        _active_registry = None


def bootstrap_phase4(memory, config: dict) -> BackgroundTaskRegistry:
    """One-shot startup wiring, called from main.py.

    - Registers Phase 4 consent channels (vision_background, and
      notification_summarization if DR-P4-09 is approved).
    - Creates the BackgroundTaskRegistry bound to the flattened phase4
      config (so TaskSpec.enabled_flag lookups work).
    - Registers the 9 task specs from P4_TASK_IDS.
    - Sets the active-registry singleton so feature modules can call
      register_p4_handler() from their own commits.
    - Does NOT start any timers. Each feature commit supplies its own
      tick driver.

    Idempotent: a second call returns the existing registry.
    """
    existing = get_active_registry()
    if existing is not None:
        return existing

    p4_cfg = phase4_config(config)
    register_phase4_consent_channels(memory, config=config)

    registry = BackgroundTaskRegistry(
        consent_manager=memory,
        config=p4_cfg,
        logger=_p4_log,
    )
    register_phase4_tasks(registry)
    set_active_registry(registry)
    _p4_log.info(
        "p4_bootstrapped",
        extra={
            "tasks": len(P4_TASK_IDS),
            "auto_summary_enabled": p4_cfg["auto_summary_enabled"],
            "continuous_enabled": p4_cfg["continuous_enabled"],
        },
    )
    return registry
