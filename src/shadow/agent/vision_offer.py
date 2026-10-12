"""VisionOfferPolicy — decides when to offer vision.

Tracks per-process cooldowns and session-scoped exclusions. The
popup is offered only when:

  - The screen changed this tick
  - UIA + OCR produced thin text (< 200 chars total)
  - The window category is visual-friendly
  - The process is not excluded
  - The cooldown window has elapsed for this process

Exclusions are session-scoped here. Commit 12 promotes them to a
persistent table.
"""

import time

# Categories that benefit from vision.
VISUAL_CATEGORIES = frozenset(
    {
        "browser",
        "document",
        "notes",
        "other",
    }
)

# Threshold below which a window is considered "visual only".
THIN_TEXT_THRESHOLD_CHARS = 200

DEFAULT_COOLDOWN_MIN = 15


class VisionOfferPolicy:
    """Decides whether to show the vision popup for a given window."""

    def __init__(
        self,
        cooldown_min: int = DEFAULT_COOLDOWN_MIN,
        enabled: bool = True,
    ):
        self.cooldown_min = int(cooldown_min)
        self.enabled = bool(enabled)
        self._cooldowns: dict[str, float] = {}
        self._excluded: set[str] = set()

    # ---------- public API ----------

    def should_offer(self, process: str, category: str) -> bool:
        if not self.enabled:
            return False
        if category not in VISUAL_CATEGORIES:
            return False

        key = self._normalize(process)
        if not key:
            return False
        if key in self._excluded:
            return False

        last = self._cooldowns.get(key)
        if last is None:
            return True  # never seen before

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
            self._excluded.add(key)

    def is_excluded(self, process: str) -> bool:
        return self._normalize(process) in self._excluded

    def excluded_processes(self) -> set[str]:
        return set(self._excluded)

    def clear_exclusions(self) -> None:
        """Clear both exclusions and cooldowns.

        Called when the user wants to reset all offer state — this
        should restore immediate offers, not just unblock the process
        but keep it on cooldown.
        """
        self._excluded.clear()
        self._cooldowns.clear()

    def seconds_until_ready(self, process: str) -> int:
        key = self._normalize(process)
        if key in self._excluded:
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
