# Phase 4 — Shared Background Task Registry (G4)

Status: PROPOSED — requires review before C05 implementation.
Owner: <your name>
Date: <date>

## 1. Problem

The audited branch has no generic background scheduler. The only worker is
`ObservationWorker` (QThread) in `src/shadow/perception/observer.py`, which is a
perception loop, not a registry. Phase 4 needs one scheduler for:

- p4.vision.auto_summary        (10-min interval)
- p4.vision.continuous          (1/3/5-min interval, mutually exclusive with auto_summary)
- p4.digest.daily               (optional schedule, off by default)
- p4.digest.weekly              (optional schedule, off by default)
- p4.weaver.run                 (user or optional schedule)
- p4.asr.job                    (user import; single-concurrency)
- p4.notifications.listener     (OS event; gated by DR-P4-06)
- p4.silent_pair.eval          (context change; yields to chat)
- p4.clone.sweep               (startup + hourly)

No feature may create its own QTimer / threading.Timer / Thread.

## 2. Task spec

    TaskSpec:
      id: str                      # "p4.vision.auto_summary"
      kind: str                    # "interval" | "cron" | "event" | "startup"
      trigger: dict                # {interval_sec: 600} | {cron: "0 18 * * *"} | {event: "uia_change"}
      dedup_key: Callable[[ctx], str]   # e.g. lambda c: f"digest:daily:{c.local_date}"
      serialization_group: str     # "vision_bg" | "lm_bg" | "asr" | "maintenance" | "listener" | "lm_fg"
      priority: int                # 0 (high) .. 9 (low)
      cancellable: bool
      consent_channels: list[str]  # must all be granted; rechecked each tick
      enabled_flag: str | None     # config key, e.g. "auto_summary_enabled"
      retry: RetryPolicy
      handler: Callable[[TaskContext], None]
      status_probe: Callable[[], TaskStatus]   # for truthful UI

## 3. Serialization groups (from PRD §22.11)

- vision_bg    — Auto-Summary and Continuous are mutually exclusive; Continuous supersedes.
- lm_bg        — digests, weekly, weaver, silent_pair yield to chat (lm_fg).
- asr          — single-concurrency; must not run with vision inference on 16 GB.
- listener     — OS notification listener, singleton.
- lm_fg        — chat (existing); background yields.
- maintenance  — clone sweep, retention prune, startup sweep.

Rule: at most one task per group runs at a time. Same task key cannot run twice
concurrently (dedup).

## 4. Lifecycle

- register(spec)      — adds spec; validates group/dedup/consent config.
- start()             — begins dispatch loop; called from main.py after app ready.
- tick(task_id)       — checks enabled flag, consent, dedup, group lock, then runs handler in worker.
- cancel(task_id)     — cooperative cancel token; handler must check between checkpoints; stop ≤ 2 s.
- pause(task_id, reason) — used on 3 consecutive failures (30 min) or battery/idle.
- shutdown()          — cancel all; wait ≤ 5 s; no writes after cancel.

Consent revocation: registry subscribes to the consent manager. On revocation,
all tasks whose consent_channels include that channel are cancelled, their in-flight
results discarded, and ephemeral data deleted via the feature's cleanup hook.

## 5. Status (for FR-P4-VUI-02 truthful status)

    TaskStatus:
      mode: "Off" | "Auto-Summary" | "Continuous" | "Paused" | "Auto-disabled" | "Unavailable" | "Not running"
      running: bool
      last_run: datetime | None
      last_error_code: str | None
      effective_rate: str | None   # e.g. "30/hr cap"
      reason: str | None

The Vision Settings UI reads live TaskStatus, never config flags.

## 6. Retry / backoff

- Vision tick: 1 retry next tick; 3 consecutive failures → pause 30 min.
- DB lock: 3 retries, exponential backoff (100ms/400ms/1600ms), then fail the unit of work.
- No tight loops. No queue growth.

## 7. Integration

- Constructed in src/shadow/main.py after MemoryStore, consent manager, config.
- ObservationWorker remains independent; the registry does not replace it.
- Task handlers run off the Qt UI thread (worker pool). UI thread never blocks > 100 ms.

## 8. Testing

- dedup: same key twice → one run.
- serialization: two vision_bg tasks → one runs, other queued or skipped.
- cancel: stop ≤ 2 s.
- shutdown: all tasks stopped ≤ 5 s, no writes after cancel.
- consent revocation: in-flight cancelled, ephemeral cleaned.
- retry: 3 failures → paused 30 min, status visible.
- status probe: reflects live state, not config.

## 9. Open questions for review

1. Should dedup keys persist across restart (e.g. digest already ran today) or be in-memory only?
   Proposal: persist for digests/weekly (unique constraint on digest period+revision); in-memory for ticks.
2. Worker pool size: 2 (one for vision_bg, one for lm_bg) or a small pool of 3? Proposal: 3.
3. Should the registry own the 8h idle auto-disable for Continuous, or should the feature?
   Proposal: feature owns domain logic; registry exposes idle hook.