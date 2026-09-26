"""SHADOW perception layer — sources that observe the user's context."""

from .base import PerceptionSource
from .active_window import ActiveWindowSource, ActiveWindow
from .screen_ocr import ScreenOCRSource
from .observer import ObservationWorker

__all__ = [
    "PerceptionSource",
    "ActiveWindowSource",
    "ActiveWindow",
    "ScreenOCRSource",
    "ObservationWorker",
]
