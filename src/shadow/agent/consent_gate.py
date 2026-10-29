"""Phase 4 consent gate (C03).

Fail-closed check helper used by user-initiated Phase 4 features (chat,
dialogs, direct invocation). Background features use TaskSpec.consent_channels
via BackgroundTaskRegistry — this gate is not a replacement for that path.

New channels registered by this commit:
  - vision_background            (Auto-Summary, Continuous — DR-P4-08)
  - notification_summarization   (only if DR-P4-09 is approved)

Per PRD §22.7 stop condition, notification_summarization is NOT registered
unless config[DR_P4_09_APPROVED_KEY] is truthy. Existing channels
(screen_capture, vision, vision_cloud, meeting_audio, etc.) are unchanged.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Channel constants
# ---------------------------------------------------------------------------
CHANNEL_VISION_BACKGROUND = "vision_background"
CHANNEL_NOTIFICATION_SUMMARIZATION = "notification_summarization"

DR_P4_09_APPROVED_KEY = "phase4.dr_p4_09_approved"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class ConsentDenied(Exception):
    """Raised by ConsentGate.require() when a channel is not granted."""

    def __init__(self, channel: str) -> None:
        self.channel = channel
        super().__init__(f"consent denied for channel '{channel}'")


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------
@dataclass
class ConsentGate:
    """Fail-closed check helper. Safe to construct once and reuse."""

    store: object  # duck-typed: has get_consent(channel) -> bool | None

    def check(self, channel: str) -> bool:
        """Return True only if the store explicitly says the channel is granted.

        Any error (missing method, missing row, exception) is treated as denied.
        """
        if not channel:
            return False
        try:
            val = self.store.get_consent(channel)  # type: ignore[attr-defined]
        except Exception:
            return False
        return val is True

    def require(self, channel: str) -> None:
        """Raise ConsentDenied if the channel is not granted."""
        if not self.check(channel):
            raise ConsentDenied(channel)

    def all_granted(self, channels: Iterable[str]) -> bool:
        """AND semantics: every channel must be granted. Empty list = False."""
        chs = list(channels)
        if not chs:
            return False
        return all(self.check(c) for c in chs)

    def any_denied(self, channels: Iterable[str]) -> str | None:
        """Return the first denied channel, or None if all granted."""
        for c in channels:
            if not self.check(c):
                return c
        return None


# ---------------------------------------------------------------------------
# Channel registration
# ---------------------------------------------------------------------------
def register_phase4_consent_channels(store, config=None) -> list[str]:
    """Register Phase 4 channels in the consent store (idempotent).

    - vision_background: always registered with default False (DR-P4-08).
    - notification_summarization: registered only if DR-P4-09 is approved
      (config[DR_P4_09_APPROVED_KEY] truthy). Default: not registered.

    Returns the list of channels that were newly inserted.
    """
    added: list[str] = []

    def _ensure(channel: str) -> None:
        if hasattr(store, "ensure_consent"):
            if store.ensure_consent(channel, granted=False):
                added.append(channel)
            return
        # Fallback for test doubles that only have get_consent/set_consent.
        try:
            current = store.get_consent(channel)
        except Exception:
            current = None
        if current is None:
            store.set_consent(channel, False)
            added.append(channel)

    _ensure(CHANNEL_VISION_BACKGROUND)

    approved = False
    if config is not None:
        try:
            approved = bool(config.get(DR_P4_09_APPROVED_KEY, False))
        except Exception:
            approved = False
    if approved:
        _ensure(CHANNEL_NOTIFICATION_SUMMARIZATION)

    return added
