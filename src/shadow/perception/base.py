from abc import ABC, abstractmethod
from typing import Any


class PerceptionSource(ABC):
    """A single observation channel (active window, OCR, typing, etc.).

    Every source:
    - has a stable `name` used as `source` in the observations table
    - has a `channel` used for consent gating (matches a consent key)
    - returns a payload dict or None from `sample()`
    """

    name: str = "unnamed"
    channel: str = "unknown"

    @abstractmethod
    def sample(self) -> dict[str, Any] | None:
        """Read the current state of this source.

        Return a JSON-serializable dict on success, or None if there is
        nothing to report right now (e.g. no active window, user idle).
        """
        ...

    def stop(self) -> None:
        """Optional cleanup. Called when the observer stops."""
        pass
