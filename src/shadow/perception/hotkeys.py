"""Global hotkey listener for vision shortcuts.

Ctrl+Shift+V — vision the active window immediately.
Ctrl+Shift+Q — region capture (stub in Commit 6, real in Commit 13).

Uses pynput's GlobalHotKeys. The listener runs on a daemon thread;
callers handle the actual work on their own thread and update the UI
via Qt signals.

Only enabled when the platform is Windows and pynput is available.
"""

import sys
import threading
import time

from PySide6.QtCore import QObject, Signal

# Debounce identical hotkey presses within this many milliseconds.
DEBOUNCE_MS = 500


class VisionHotkeys(QObject):
    """Emits signals when vision hotkeys are pressed."""

    vision_requested = Signal()
    region_capture_requested = Signal()

    def __init__(self, enabled: bool = True):
        super().__init__()
        self._listener = None
        self._enabled = bool(enabled)
        self._lock = threading.Lock()
        self._last_vision_at = 0.0
        self._last_region_at = 0.0

    # ---------- lifecycle ----------

    def start(self) -> None:
        if not self._enabled:
            return
        if sys.platform != "win32":
            return
        if self._listener is not None:
            return

        try:
            from pynput import keyboard
        except ImportError:
            return

        try:
            self._listener = keyboard.GlobalHotKeys(
                {
                    "<ctrl>+<shift>+v": self._on_vision,
                    "<ctrl>+<shift>+q": self._on_region,
                }
            )
            self._listener.daemon = True
            self._listener.start()
        except Exception:
            self._listener = None

    def stop(self) -> None:
        with self._lock:
            if self._listener is not None:
                try:
                    self._listener.stop()
                except Exception:
                    pass
                self._listener = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, value: bool) -> None:
        self._enabled = bool(value)
        if not self._enabled:
            self.stop()
        else:
            self.start()

    # ---------- hotkey handlers ----------

    def _on_vision(self) -> None:
        now = time.monotonic()
        if (now - self._last_vision_at) * 1000 < DEBOUNCE_MS:
            return
        self._last_vision_at = now
        try:
            self.vision_requested.emit()
        except Exception:
            pass

    def _on_region(self) -> None:
        now = time.monotonic()
        if (now - self._last_region_at) * 1000 < DEBOUNCE_MS:
            return
        self._last_region_at = now
        try:
            self.region_capture_requested.emit()
        except Exception:
            pass
