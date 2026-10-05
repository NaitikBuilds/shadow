"""Screen Change Detection — perceptual hashing to skip unchanged frames.

Uses dhash (difference hash) — resize to 9x8 grayscale, compare adjacent
pixels, produce a 64-bit hash. Two frames are "the same" if their
Hamming distance is below a threshold.

This is the mechanism the observer uses to skip OCR/UIA extraction when
nothing has changed. It does not store images, hashes, or decisions —
only compares and returns a boolean.
"""

import sys
import time
from typing import Any


class ChangeDetector:
    """Detects whether the active screen region has meaningfully changed."""

    def __init__(
        self,
        threshold: int = 5,
        hash_size: int = 8,
        min_interval_ms: int = 500,
        monitor_aware: bool = True,
    ):
        self.threshold = threshold
        self.hash_size = hash_size
        self.min_interval_ms = min_interval_ms
        self._monitor_aware = monitor_aware

        self._last_hash: int | None = None
        self._last_check_at: float = 0.0
        self._last_result: bool = True

    # ---------- public API ----------

    def has_changed(self, bbox: tuple[int, int, int, int] | None = None) -> bool:
        """Return True if the region has changed since the last check.

        `bbox` is (left, top, right, bottom) in screen coordinates.
        If None, the entire screen is captured.

        Cached within min_interval_ms to prevent re-grabbing too often.
        """
        if sys.platform != "win32":
            return True

        if bbox is None and self._monitor_aware:
            try:
                from .monitors import active_monitor

                m = active_monitor()
                if m is not None:
                    bbox = m.bounds
            except Exception:
                pass

        now = time.monotonic()
        if now - self._last_check_at < self.min_interval_ms / 1000.0:
            return self._last_result

        self._last_check_at = now

        try:
            img = self._capture(bbox)
        except Exception:
            self._last_result = True
            return True

        if img is None:
            self._last_result = True
            return True

        try:
            current = self._dhash(img)
        except Exception:
            self._last_result = True
            return True

        if self._last_hash is None:
            self._last_hash = current
            self._last_result = True
            return True

        distance = self._hamming(self._last_hash, current)
        changed = distance > self.threshold
        self._last_hash = current
        self._last_result = changed
        return changed

    def reset(self) -> None:
        """Clear cached state. Next has_changed() will always return True."""
        self._last_hash = None
        self._last_check_at = 0.0
        self._last_result = True

    def info(self) -> dict:
        return {
            "threshold": self.threshold,
            "hash_size": self.hash_size,
            "min_interval_ms": self.min_interval_ms,
            "has_hash": self._last_hash is not None,
        }

    # ---------- internals ----------

    @staticmethod
    def _capture(bbox: tuple[int, int, int, int] | None) -> Any:
        try:
            from PIL import ImageGrab
        except ImportError:
            return None
        try:
            return ImageGrab.grab(bbox=bbox) if bbox else ImageGrab.grab()
        except Exception:
            return None

    def _dhash(self, img) -> int:
        """Compute a difference hash: 64 bits by default."""
        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("Pillow not available") from exc

        # Resize to (hash_size + 1) x hash_size grayscale
        resized = img.convert("L").resize(
            (self.hash_size + 1, self.hash_size),
            Image.Resampling.LANCZOS,
        )
        # tobytes() returns one byte per pixel for "L" mode — faster
        # than getdata() and not deprecated.
        pixels = resized.tobytes()

        bits: list[str] = []
        row_len = self.hash_size + 1
        for row in range(self.hash_size):
            for col in range(self.hash_size):
                left = pixels[row * row_len + col]
                right = pixels[row * row_len + col + 1]
                bits.append("1" if left > right else "0")

        return int("".join(bits), 2)

    @staticmethod
    def _hamming(a: int, b: int) -> int:
        return bin(a ^ b).count("1")
