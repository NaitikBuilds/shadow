"""SHADOW perception layer — sources that observe the user's context."""

from .base import PerceptionSource
from .active_window import ActiveWindowSource, ActiveWindow

__all__ = ["PerceptionSource", "ActiveWindowSource", "ActiveWindow"]
