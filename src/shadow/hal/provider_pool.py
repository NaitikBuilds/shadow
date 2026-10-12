"""ProviderPool — multi-provider failover for cloud LLM backends.

Holds multiple CloudBackend instances, tries them in priority order,
and falls back to a local backend when all cloud providers are
unavailable.

Tracks per-provider cooldowns so a rate-limited provider isn't
hammered on every subsequent request.
"""

import time
from collections.abc import Iterator
from dataclasses import dataclass

from .base import InferenceBackend
from .cloud_backend import (
    AuthError,
    CloudBackend,
    NetworkError,
    RateLimitError,
    ServerError,
)

# Cooldown durations in seconds, by failure type.
COOLDOWN_RATE_LIMIT = 60
COOLDOWN_SERVER_ERROR = 30
COOLDOWN_NETWORK = 15
COOLDOWN_AUTH = 24 * 3600  # permanent until restart or key update


class AllProvidersFailed(Exception):
    """Raised when every cloud provider and the local fallback fail."""

    def __init__(self, message: str, tried: list[str]):
        super().__init__(message)
        self.tried = tried


@dataclass
class ProviderState:
    """Runtime state for one provider in the pool."""

    backend: CloudBackend
    priority: int
    cooldown_until: float = 0.0
    last_error: str = ""
    last_success_at: float = 0.0
    consecutive_failures: int = 0

    @property
    def is_available(self) -> bool:
        return time.monotonic() >= self.cooldown_until

    @property
    def cooldown_remaining(self) -> int:
        remaining = self.cooldown_until - time.monotonic()
        return max(0, int(remaining))


class ProviderPool(InferenceBackend):
    """Multi-provider cloud LLM backend with priority failover.

    Args:
        providers: list of (priority, CloudBackend) tuples.
        local_fallback: optional local InferenceBackend used when
            all cloud providers are unavailable.
    """

    def __init__(
        self,
        providers: list[tuple[int, CloudBackend]],
        local_fallback: InferenceBackend | None = None,
    ):
        self._states: list[ProviderState] = [
            ProviderState(backend=backend, priority=priority)
            for priority, backend in sorted(providers, key=lambda x: x[0])
        ]
        self._local_fallback = local_fallback

    # ---------- public API ----------

    def generate(self, prompt: str, **kwargs) -> str:
        return "".join(self.generate_stream(prompt, **kwargs)).strip()

    def generate_stream(self, prompt: str, **kwargs) -> Iterator[str]:
        tried: list[str] = []
        for state in self._states:
            if not state.is_available:
                continue
            tried.append(state.backend.provider.name)
            try:
                yield from state.backend.generate_stream(prompt, **kwargs)
                state.last_success_at = time.monotonic()
                state.consecutive_failures = 0
                state.last_error = ""
                return
            except RateLimitError as exc:
                self._cool_down(state, COOLDOWN_RATE_LIMIT, exc)
                continue
            except AuthError as exc:
                self._cool_down(state, COOLDOWN_AUTH, exc)
                continue
            except ServerError as exc:
                self._cool_down(state, COOLDOWN_SERVER_ERROR, exc)
                continue
            except NetworkError as exc:
                self._cool_down(state, COOLDOWN_NETWORK, exc)
                continue

        # All cloud providers unavailable
        if self._local_fallback is not None:
            yield from self._local_fallback.generate_stream(prompt, **kwargs)
            return

        raise AllProvidersFailed(
            "all cloud providers unavailable and no local fallback",
            tried,
        )

    def embed(self, text: str) -> list[float]:
        if self._local_fallback is not None:
            return self._local_fallback.embed(text)
        raise NotImplementedError(
            "ProviderPool does not embed. Use the local ONNX embedder."
        )

    def understand_image(
        self,
        image_bytes: bytes,
        task: str = "caption",
        prompt: str = "",
    ) -> str:
        """Delegate vision to the local fallback.

        Cloud providers may eventually support vision. For now, vision
        is always local.
        """
        if self._local_fallback is not None:
            return self._local_fallback.understand_image(
                image_bytes, task=task, prompt=prompt
            )
        raise NotImplementedError(
            "ProviderPool has no vision support and no local fallback."
        )

    def supports_vision(self) -> bool:
        if self._local_fallback is not None:
            return self._local_fallback.supports_vision()
        return False

    @property
    def info(self) -> dict:
        available = [s for s in self._states if s.is_available]
        return {
            "backend": "cloud_pool",
            "provider_count": len(self._states),
            "available_count": len(available),
            "has_local_fallback": self._local_fallback is not None,
            "providers": [s.backend.provider.name for s in self._states],
        }

    def status(self) -> list[dict]:
        """Per-provider status for the UI."""
        now = time.monotonic()
        result = []
        for s in self._states:
            if not s.backend.provider.api_key:
                state = "no_key"
            elif not s.is_available:
                state = "cooldown"
            elif s.consecutive_failures > 0:
                state = "degraded"
            else:
                state = "ready"
            result.append(
                {
                    "name": s.backend.provider.name,
                    "model": s.backend.provider.model,
                    "priority": s.priority,
                    "state": state,
                    "cooldown_remaining": s.cooldown_remaining,
                    "last_error": s.last_error,
                    "last_success_ago": (
                        int(now - s.last_success_at) if s.last_success_at > 0 else None
                    ),
                }
            )
        return result

    def mark_key_updated(self, provider_name: str) -> None:
        """Clear cooldown and error state after a key change."""
        for state in self._states:
            if state.backend.provider.name == provider_name:
                state.cooldown_until = 0.0
                state.last_error = ""
                state.consecutive_failures = 0
                return

    def close(self) -> None:
        for state in self._states:
            state.backend.close()
        if self._local_fallback is not None and hasattr(self._local_fallback, "close"):
            self._local_fallback.close()

    # ---------- internals ----------

    @staticmethod
    def _cool_down(state: ProviderState, seconds: int, exc: Exception) -> None:
        state.cooldown_until = time.monotonic() + seconds
        state.last_error = str(exc)
        state.consecutive_failures += 1
