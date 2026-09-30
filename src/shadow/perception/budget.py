"""Adaptive Observation Budget — dynamic tick interval.

Reads activity, battery state, and mode to compute an effective tick
interval. Slows down when the user is idle or on battery; speeds up
when context is changing quickly.

Failsafe: any error falls back to the base mode interval.
"""

from datetime import datetime, timedelta

from shadow.config import tick_interval


class BudgetController:
    """Computes the effective observation interval from multiple signals."""

    def __init__(self, memory, config):
        self.memory = memory
        self.config = config
        self.pcfg = config.get("perception") or {}
        self.bcfg = self.pcfg.get("budget") or {}

        self.enabled = bool(self.bcfg.get("enabled", True))
        self.active_multiplier = float(self.bcfg.get("active_multiplier", 0.7))
        self.idle_multiplier = float(self.bcfg.get("idle_multiplier", 1.5))
        self.battery_multiplier = float(self.bcfg.get("battery_multiplier", 1.5))
        self.low_battery_threshold = int(self.bcfg.get("low_battery_threshold", 20))
        self.low_battery_multiplier = float(
            self.bcfg.get("low_battery_multiplier", 2.0)
        )
        self.min_interval = int(self.bcfg.get("min_interval_sec", 5))
        self.max_interval = int(self.bcfg.get("max_interval_sec", 180))

    def effective_interval(self, mode: str) -> int:
        """Return the effective tick interval in seconds.

        Falls back to the base interval if anything fails.
        """
        base = tick_interval(self.config, mode)
        if not self.enabled:
            return base

        try:
            multiplier = 1.0
            multiplier *= self._activity_multiplier()
            multiplier *= self._battery_multiplier()
            result = int(base * multiplier)
            return max(self.min_interval, min(self.max_interval, result))
        except Exception:
            return base

    # ---------- activity ----------

    def _activity_multiplier(self) -> float:
        """Recent observation density drives speed."""
        count = self._recent_observation_count(minutes=5)
        if count >= 10:
            return self.active_multiplier
        if count <= 1:
            return self.idle_multiplier
        return 1.0

    def _recent_observation_count(self, minutes: int) -> int:
        cutoff = (datetime.now() - timedelta(minutes=minutes)).isoformat(
            sep=" ", timespec="seconds"
        )
        try:
            cur = self.memory.conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM observations WHERE timestamp >= ?",
                (cutoff,),
            )
            return int(cur.fetchone()[0] or 0)
        except Exception:
            return 0

    # ---------- battery ----------

    def _battery_multiplier(self) -> float:
        try:
            import psutil

            info = psutil.sensors_battery()
        except Exception:
            return 1.0

        if info is None:
            return 1.0  # desktop, no battery

        if info.power_plugged:
            return 1.0

        # On battery
        percent = info.percent if info.percent is not None else 100
        if percent <= self.low_battery_threshold:
            return self.low_battery_multiplier
        return self.battery_multiplier
