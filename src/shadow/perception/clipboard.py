"""Clipboard Awareness — observe what the user copies.

Polls the Windows clipboard, filters sensitive content (passwords,
API keys), and returns novel text as an observation. Gated by its
own consent channel `clipboard`.

Design: polling beats event hooks for reliability and simplicity.
2-second cadence, dedup by SHA256, no images or files.
"""

import hashlib
import re
import sys
import time
from datetime import datetime
from typing import Any

from .base import PerceptionSource

# Patterns that indicate secrets. If any matches, the content is dropped.
_SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"),  # OpenAI
    re.compile(r"\bghp_[A-Za-z0-9]{30,}\b"),  # GitHub PAT
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),  # AWS key
    re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"),  # PEM
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"),  # Slack
]

# Heuristic: long hex strings are probably tokens.
_HEX_LIKE = re.compile(r"^[a-fA-F0-9]{32,}$")

# Heuristic: long base64-like strings are probably tokens.
_BASE64_LIKE = re.compile(r"^[A-Za-z0-9+/=]{40,}$")


class ClipboardSource(PerceptionSource):
    """Polls the clipboard for novel text content."""

    name = "clipboard"
    channel = "clipboard"

    POLL_SEC = 2.0
    MIN_CHARS = 10
    MAX_CHARS = 10_000
    DEDUPE_WINDOW_SEC = 60

    def __init__(self):
        self._last_hash: str = ""
        self._last_hash_at: float = 0.0
        self._last_poll: float = 0.0
        self._cached_text: str = ""

    def sample(self) -> dict[str, Any] | None:
        if sys.platform != "win32":
            return None

        now = time.monotonic()
        if now - self._last_poll < self.POLL_SEC:
            return None
        self._last_poll = now

        text = self._read_clipboard()
        if not text:
            return None

        text = text.strip()
        if len(text) < self.MIN_CHARS:
            return None
        if len(text) > self.MAX_CHARS:
            text = text[: self.MAX_CHARS]

        if self._looks_like_secret(text):
            return None

        h = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
        if h == self._last_hash and (now - self._last_hash_at) < self.DEDUPE_WINDOW_SEC:
            return None

        self._last_hash = h
        self._last_hash_at = now
        self._cached_text = text

        return {
            "content": text,
            "chars": len(text),
            "sha256": h,
            "timestamp": datetime.utcnow().isoformat(sep=" ", timespec="seconds"),
        }

    # ---------- internals ----------

    def _read_clipboard(self) -> str:
        try:
            import win32clipboard
        except ImportError:
            return ""

        try:
            win32clipboard.OpenClipboard()
        except Exception:
            return ""

        try:
            if not win32clipboard.IsClipboardFormatAvailable(
                win32clipboard.CF_UNICODETEXT
            ):
                return ""
            try:
                return (
                    win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT) or ""
                )
            except Exception:
                return ""
        finally:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass

    @staticmethod
    def _looks_like_secret(text: str) -> bool:
        for pat in _SECRET_PATTERNS:
            if pat.search(text):
                return True
        stripped = text.strip()
        if _HEX_LIKE.match(stripped):
            return True
        return len(stripped) >= 40 and bool(_BASE64_LIKE.match(stripped))

    def stop(self) -> None:
        self._last_hash = ""
        self._cached_text = ""
