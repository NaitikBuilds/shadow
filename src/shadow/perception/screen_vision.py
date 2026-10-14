"""ScreenVisionSource — capture the active window and run local VLM.

Unlike other perception sources, this is not part of the observer
loop. It runs only when the user (or a UI action) triggers a
vision pass: Ctrl+Shift+V, the popup prompt's Yes button, or a
region capture.

Design:
  - Captures the active window's rectangle (not the whole screen)
  - Downscales large images before sending to the vision model
  - Rejects sensitive windows (password managers, banking, private mode)
  - Never stores the image — only the caption the model returns
"""

import io
import sys
from collections.abc import Callable
from datetime import datetime
from typing import Any

from .active_window import ActiveWindowSource
from .base import PerceptionSource
from .window_classifier import WindowClassifier

# Substrings that flag a window as sensitive. Case-insensitive.
# Matching is on the window title (which usually includes the site or
# document name) and on the process name.
_SENSITIVE_PROCESS_NAMES = {
    "1password",
    "bitwarden",
    "keepass",
    "keepassxc",
    "lastpass",
    "dashlane",
    "nordpass",
}

_SENSITIVE_TITLE_MARKERS = (
    "1password",
    "bitwarden",
    "keepass",
    "lastpass",
    "dashlane",
    "nordpass",
    " - banking",
    "online banking",
    "sign in to your bank",
    "private browsing",
    "incognito",
    "inprivate",
)

DEFAULT_IMAGE_MAX_SIDE = 1024
DEFAULT_IMAGE_MAX_BYTES = 10 * 1024 * 1024


class ScreenVisionSource(PerceptionSource):
    """Captures the active window and dispatches to a vision service."""

    name = "screen_vision"
    channel = "vision"
    is_screen_source = False  # never auto-run by the observer

    def __init__(
        self,
        vision_service,
        classifier: WindowClassifier | None = None,
        capture_fn: Callable[[tuple[int, int, int, int]], Any] | None = None,
        image_max_side: int = DEFAULT_IMAGE_MAX_SIDE,
        image_max_bytes: int = DEFAULT_IMAGE_MAX_BYTES,
        exclusions=None,
    ):
        self.vision_service = vision_service
        self.classifier = classifier or WindowClassifier()
        self._capture_fn = capture_fn
        self.image_max_side = image_max_side
        self.image_max_bytes = image_max_bytes
        self.exclusions = exclusions

    # ---------- public API ----------

    def sample(
        self,
        task: str = "caption",
        prompt: str = "",
    ) -> dict[str, Any] | None:
        """Capture the active window, run vision, return payload or None.

        Args:
            task: one of caption / detailed_caption / ocr / query.
            prompt: question when task == query.

        Returns payload with:
            text, task, prompt, window_title, process, image_bytes,
            timestamp
        """
        if sys.platform != "win32":
            return None

        window = self._active_window()
        if not window:
            return None

        profile = self.classifier.classify(
            process=window.get("process", ""),
            title=window.get("title", ""),
        )
        if profile.is_self:
            return None
        if self._is_sensitive(window):
            return None

        if self.exclusions is not None:
            try:
                if self.exclusions.is_excluded(window.get("process", "")):
                    return None
            except Exception:
                pass

        rect = self._window_rect()
        if rect is None:
            return None

        image_bytes = self._capture_and_encode(rect)
        if not image_bytes:
            return None

        text = (
            self.vision_service.analyze(image_bytes, task=task, prompt=prompt)
            if self.vision_service is not None
            else ""
        )
        if not text:
            return None

        return {
            "text": text,
            "task": task,
            "prompt": prompt,
            "window_title": window.get("title", ""),
            "process": window.get("process", ""),
            "image_bytes": len(image_bytes),
            "timestamp": datetime.utcnow().isoformat(sep=" ", timespec="seconds"),
        }

    # ---------- helpers ----------

    @staticmethod
    def _active_window() -> dict | None:
        try:
            return ActiveWindowSource().sample()
        except Exception:
            return None

    @staticmethod
    def _window_rect() -> tuple[int, int, int, int] | None:
        try:
            import win32gui
        except ImportError:
            return None
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return None
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            if right <= left or bottom <= top:
                return None
            return (left, top, right, bottom)
        except Exception:
            return None

    @staticmethod
    def _is_sensitive(window: dict) -> bool:
        process = (window.get("process") or "").lower()
        process_base = process.replace(".exe", "").strip()
        if process_base in _SENSITIVE_PROCESS_NAMES:
            return True

        title = (window.get("title") or "").lower()
        return any(marker in title for marker in _SENSITIVE_TITLE_MARKERS)

    def _capture_and_encode(self, rect: tuple[int, int, int, int]) -> bytes | None:
        try:
            from PIL import Image, ImageGrab
        except ImportError:
            return None

        try:
            if self._capture_fn is not None:
                img = self._capture_fn(rect)
            else:
                img = ImageGrab.grab(bbox=rect)
        except Exception:
            return None

        if img is None:
            return None

        # Downscale to max side
        try:
            w, h = img.size
            longest = max(w, h)
            if longest > self.image_max_side:
                scale = self.image_max_side / longest
                new_size = (int(w * scale), int(h * scale))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
        except Exception:
            pass

        # Encode as PNG (lossless for text-heavy screenshots)
        try:
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            data = buf.getvalue()
        except Exception:
            return None

        # If PNG exceeds cap, re-encode as JPEG
        if len(data) > self.image_max_bytes:
            try:
                buf = io.BytesIO()
                img.convert("RGB").save(buf, format="JPEG", quality=70)
                data = buf.getvalue()
            except Exception:
                pass

        # Final hard cap
        if len(data) > self.image_max_bytes:
            return None
        return data

    def stop(self) -> None:
        # Nothing to clean up — vision service owns the model lifecycle
        pass
