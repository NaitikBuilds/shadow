"""Adaptive Cadence — dynamic active-window poll frequency.

Uses the ChangeDetector signal to shrink or grow the poll interval.
Faster when the screen is changing; slower when it's stable.

This runs alongside BudgetController (Phase 3). BudgetController picks
the observer tick interval; AdaptiveCadence refines how often we poll
the active window inside that tick.
"""

import time
from dataclasses import dataclass


@dataclass
class CadenceInfo:
    current_interval: int
    min_interval: int
    max_interval: int
    last_changed: bool
    total_samples: int
    changed_count: int


class AdaptiveCadence:
    """Adjusts poll frequency from the change signal."""

    def __init__(self, detector, config):
        self.detector = detector
        self.cfg = (config.get("perception") or {}).get("cadence") or {}

        self.enabled = bool(self.cfg.get("enabled", True))
        self.min_interval = int(self.cfg.get("min_interval_sec", 5))
        self.max_interval = int(self.cfg.get("max_interval_sec", 60))
        self.idle_interval = int(self.cfg.get("idle_interval_sec", 30))
        self.accelerate = float(self.cfg.get("accelerate_multiplier", 0.5))
        self.backoff = float(self.cfg.get("backoff_multiplier", 1.5))

        self._current_interval = self.idle_interval
        self._last_sample_at = 0.0
        self._last_changed = False
        self._total_samples = 0
        self._changed_count = 0

    # ---------- public API ----------

    def due(self) -> bool:
        """True if the current interval has elapsed since the last sample."""
        if not self.enabled:
            return True
        now = time.monotonic()
        return (now - self._last_sample_at) >= self._current_interval

    def sample(self) -> tuple[bool, int]:
        """Run change detection, adjust interval, return (changed, next_interval)."""
        self._last_sample_at = time.monotonic()
        self._total_samples += 1

        if not self.enabled:
            return False, self._current_interval

        changed = self.detector.has_changed()
        self._last_changed = changed

        if changed:
            self._changed_count += 1
            new_interval = int(self._current_interval * self.accelerate)
            self._current_interval = max(self.min_interval, new_interval)
        else:
            new_interval = int(self._current_interval * self.backoff)
            self._current_interval = min(self.max_interval, new_interval)

        return changed, self._current_interval

    @property
    def current_interval(self) -> int:
        return self._current_interval

    @property
    def last_changed(self) -> bool:
        return self._last_changed

    def info(self) -> CadenceInfo:
        return CadenceInfo(
            current_interval=self._current_interval,
            min_interval=self.min_interval,
            max_interval=self.max_interval,
            last_changed=self._last_changed,
            total_samples=self._total_samples,
            changed_count=self._changed_count,
        )

    def reset(self) -> None:
        """Reset to initial state."""
        self._current_interval = self.idle_interval
        self._last_sample_at = 0.0
        self._last_changed = False
        self._total_samples = 0
        self._changed_count = 0
