"""Network health check — detects online/offline state.

A lightweight probe against a fast, reliable endpoint. Result is
cached for `CACHE_SEC` to avoid probing on every query.

Used by HybridBackend to decide between cloud and local execution.
"""

import socket
import time

# Fast public endpoints to probe. Tried in order.
PROBE_HOSTS = [
    ("api.groq.com", 443),
    ("generativelanguage.googleapis.com", 443),
    ("1.1.1.1", 53),
]

# How long to cache a probe result.
CACHE_SEC = 60

# Socket timeout per probe.
SOCKET_TIMEOUT_SEC = 2


class HealthMonitor:
    """Tracks online/offline state with a lightweight cached probe."""

    def __init__(self, cache_sec: int = CACHE_SEC):
        self.cache_sec = cache_sec
        self._last_check_at = 0.0
        self._last_result = True  # assume online until proven otherwise

    def is_online(self) -> bool:
        """Return True if we have network connectivity.

        Cached for cache_sec so this is cheap to call repeatedly.
        """
        now = time.monotonic()
        if now - self._last_check_at < self.cache_sec:
            return self._last_result

        self._last_check_at = now
        self._last_result = self._probe()
        return self._last_result

    def force_check(self) -> bool:
        """Force an immediate probe, ignoring cache."""
        self._last_check_at = 0.0
        return self.is_online()

    def info(self) -> dict:
        return {
            "online": self._last_result,
            "last_check_ago_sec": (
                int(time.monotonic() - self._last_check_at)
                if self._last_check_at > 0
                else None
            ),
            "cache_sec": self.cache_sec,
        }

    # ---------- internals ----------

    @staticmethod
    def _probe() -> bool:
        for host, port in PROBE_HOSTS:
            try:
                with socket.create_connection((host, port), timeout=SOCKET_TIMEOUT_SEC):
                    return True
            except (TimeoutError, OSError):
                continue
        return False
