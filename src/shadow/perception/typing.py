import threading
import time
from datetime import datetime
from typing import Any

from .base import PerceptionSource


class TypingDynamicsSource(PerceptionSource):
    """Tracks keystroke timing patterns to estimate focus and cognitive load.

    IMPORTANT: This source observes timing only. It never records which key
    was pressed. The callback receives the key object from pynput and
    discards it immediately — only the monotonic timestamp is retained.
    """

    name = "typing_dynamics"
    channel = "typing_dynamics"

    PAUSE_THRESHOLD_SEC = 2.0
    MIN_KEYSTROKES = 10  # don't emit an observation for tiny bursts

    def __init__(self, pause_threshold_sec: float = 2.0, min_keystrokes: int = 10):
        self.PAUSE_THRESHOLD_SEC = pause_threshold_sec
        self.MIN_KEYSTROKES = min_keystrokes
        self._lock = threading.Lock()
        self._events: list[float] = []
        self._listener = None
        self._started = False
        self._start()

    # ---------- lifecycle ----------

    def _start(self) -> None:
        try:
            from pynput import keyboard
        except ImportError:
            return

        def on_press(_key):
            # Deliberately ignore the key value. Record timing only.
            now = time.monotonic()
            with self._lock:
                self._events.append(now)

        try:
            self._listener = keyboard.Listener(on_press=on_press)
            self._listener.daemon = True
            self._listener.start()
            self._started = True
        except Exception:
            self._listener = None
            self._started = False

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
            self._started = False

    # ---------- sampling ----------

    def sample(self) -> dict[str, Any] | None:
        if not self._started:
            return None

        with self._lock:
            events = self._events
            self._events = []

        if len(events) < self.MIN_KEYSTROKES:
            return None

        events.sort()
        intervals = [events[i + 1] - events[i] for i in range(len(events) - 1)]
        duration = events[-1] - events[0]
        if duration <= 0:
            return None

        pauses = [i for i in intervals if i >= self.PAUSE_THRESHOLD_SEC]
        longest_pause = max(intervals) if intervals else 0.0
        mean_interval = sum(intervals) / len(intervals) if intervals else 0.0
        kpm = (len(events) / duration) * 60.0

        focus_score = self._focus_score(kpm, mean_interval, len(pauses))
        summary = (
            f"Typing activity: {len(events)} keystrokes over "
            f"{duration:.0f}s ({kpm:.0f} KPM, avg interval "
            f"{mean_interval * 1000:.0f}ms, {len(pauses)} pauses > "
            f"{self.PAUSE_THRESHOLD_SEC:.0f}s, longest pause "
            f"{longest_pause:.1f}s, focus {focus_score:.2f})"
        )

        return {
            "keystrokes": len(events),
            "duration_sec": round(duration, 1),
            "kpm": round(kpm, 1),
            "mean_interval_ms": round(mean_interval * 1000, 1),
            "pause_count": len(pauses),
            "longest_pause_sec": round(longest_pause, 1),
            "focus_score": round(focus_score, 2),
            "summary": summary,
            "timestamp": datetime.utcnow().isoformat(sep=" ", timespec="seconds"),
        }

    @staticmethod
    def _focus_score(kpm: float, mean_interval: float, pause_count: int) -> float:
        """Heuristic 0–1: steady rhythm at moderate speed scores highest.

        - Very slow (<10 KPM) → probably idle or thinking → low
        - Very fast (>120 KPM) → probably rote typing → mid
        - Steady 40–80 KPM with few long pauses → high
        """
        if kpm < 10:
            speed = kpm / 10.0
        elif kpm > 120:
            speed = max(0.0, 1.0 - (kpm - 120) / 120.0)
        else:
            speed = 1.0 - abs(kpm - 60.0) / 60.0
            speed = max(0.0, min(1.0, speed))
        pause_penalty = min(pause_count * 0.05, 0.4)
        return max(0.0, min(1.0, speed - pause_penalty))
