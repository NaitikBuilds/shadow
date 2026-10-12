"""HybridBackend — routes between cloud and local based on connectivity.

Wraps a ProviderPool (cloud) and a local backend. When the network is
available and cloud is enabled, calls go to the pool. When offline,
calls go straight to the local backend.

The pool itself has its own local fallback for per-provider exhaustion.
This backend adds the top-level online/offline gate.
"""

from collections.abc import Iterator

from .base import InferenceBackend
from .health import HealthMonitor


class HybridBackend(InferenceBackend):
    """Routes between cloud and local based on connectivity state."""

    def __init__(
        self,
        cloud: InferenceBackend,
        local: InferenceBackend,
        health: HealthMonitor | None = None,
    ):
        self.cloud = cloud
        self.local = local
        self.health = health or HealthMonitor()
        self._last_used: str = "unknown"
        self.last_prompt_at: float = 0.0

    # ---------- public API ----------

    def generate(self, prompt: str, **kwargs) -> str:
        return "".join(self.generate_stream(prompt, **kwargs)).strip()

    def generate_stream(self, prompt: str, **kwargs) -> Iterator[str]:
        import time as _time

        self.last_prompt_at = _time.time()

        if self.health.is_online():
            self._last_used = "cloud"
            try:
                yield from self.cloud.generate_stream(prompt, **kwargs)
                return
            except Exception:
                # Any cloud failure → local
                self._last_used = "local_fallback"
                yield from self.local.generate_stream(prompt, **kwargs)
                return

        self._last_used = "local_offline"
        yield from self.local.generate_stream(prompt, **kwargs)

    def embed(self, text: str) -> list[float]:
        return self.local.embed(text)

    def understand_image(
        self,
        image_bytes: bytes,
        task: str = "caption",
        prompt: str = "",
    ) -> str:
        """Vision always uses the local backend.

        Cloud vision is not in v1.0. When it arrives, this method
        gains a routing branch identical to generate_stream.
        """
        return self.local.understand_image(image_bytes, task=task, prompt=prompt)

    def supports_vision(self) -> bool:
        return self.local.supports_vision()

    @property
    def info(self) -> dict:
        local_info = self.local.info if hasattr(self.local, "info") else {}
        cloud_info = self.cloud.info if hasattr(self.cloud, "info") else {}
        return {
            "backend": "hybrid",
            "route": self._last_used,
            "online": self.health.is_online(),
            "local": local_info,
            "cloud": cloud_info,
            "last_prompt": self.last_prompt,
            "last_prompt_at": self.last_prompt_at,
        }

    @property
    def last_prompt(self) -> str:
        """Return the most recent prompt actually sent, or empty."""
        # Pull from the cloud provider if it ran; else fall back to local.
        if self._last_used.startswith("cloud"):
            for state in getattr(self.cloud, "_states", []):
                if state.backend.last_prompt:
                    return state.backend.last_prompt
        return ""

    def close(self) -> None:
        for backend in (self.cloud, self.local):
            if hasattr(backend, "close"):
                try:
                    backend.close()
                except Exception:
                    pass
