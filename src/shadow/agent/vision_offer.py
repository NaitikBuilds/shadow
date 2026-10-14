"""VisionOfferPolicy — decides when to offer vision.

Exclusions are persisted in the vision_exclusions table (Commit 12).
Cooldowns remain session-scoped — resetting on restart is fine for
"don't ask again in 15 minutes".

Pass `exclusions=None` to skip persistent checks (used in tests).
"""

import time

VISUAL_CATEGORIES = frozenset(
    {
        "browser",
        "document",
        "notes",
        "other",
    }
)

THIN_TEXT_THRESHOLD_CHARS = 200

DEFAULT_COOLDOWN_MIN = 15


class VisionOfferPolicy:
    """Decides whether to show the vision popup for a given window."""

    def __init__(
        self,
        cooldown_min: int = DEFAULT_COOLDOWN_MIN,
        enabled: bool = True,
        exclusions=None,
    ):
        self.cooldown_min = int(cooldown_min)
        self.enabled = bool(enabled)
        self.exclusions = exclusions  # VisionExclusionStore or None
        self._cooldowns: dict[str, float] = {}
        self._local_exclusions: set[str] = set()

    # ---------- public API ----------

    def should_offer(self, process: str, category: str) -> bool:
        if not self.enabled:
            return False
        if category not in VISUAL_CATEGORIES:
            return False

        key = self._normalize(process)
        if not key:
            return False

        if self.exclusions is not None and self.exclusions.is_excluded(key):
            return False

        last = self._cooldowns.get(key)
        if last is None:
            return True

        elapsed = time.monotonic() - last
        return elapsed >= (self.cooldown_min * 60)

    def record(self, process: str, choice: str) -> None:
        """Record a user's choice for this process.

        choice: "yes" | "not_now" | "never"
        """
        key = self._normalize(process)
        if not key:
            return
        self._cooldowns[key] = time.monotonic()
        if choice == "never":
            if self.exclusions is not None:
                self.exclusions.exclude(key, reason="user")
            else:
                self._local_exclusions.add(key)

    def is_excluded(self, process: str) -> bool:
        key = self._normalize(process)
        if self.exclusions is not None:
            return self.exclusions.is_excluded(key)
        return key in self._local_exclusions

    def excluded_processes(self) -> set[str]:
        if self.exclusions is not None:
            return {e["process"] for e in self.exclusions.all_excluded()}
        return set()

    def clear_exclusions(self) -> None:
        if self.exclusions is not None:
            self.exclusions.clear_all()
        self._local_exclusions.clear()
        self._cooldowns.clear()

    def seconds_until_ready(self, process: str) -> int:
        key = self._normalize(process)
        if self.is_excluded(key):
            return -1
        last = self._cooldowns.get(key)
        if last is None:
            return 0
        remaining = (self.cooldown_min * 60) - (time.monotonic() - last)
        return max(0, int(remaining))

    # ---------- internals ----------

    @staticmethod
    def _normalize(process: str) -> str:
        if not process:
            return ""
        return process.strip().lower().replace(".exe", "")
