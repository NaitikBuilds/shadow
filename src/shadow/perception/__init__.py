"""SHADOW perception layer — sources that observe the user's context."""

from .active_window import ActiveWindow, ActiveWindowSource
from .base import PerceptionSource
from .calendar import CalendarSource
from .calendar_winrt import WindowsCalendarSource
from .documents import DocumentSource
from .observer import ObservationWorker
from .screen_ocr import ScreenOCRSource
from .typing import TypingDynamicsSource

__all__ = [
    "PerceptionSource",
    "ActiveWindowSource",
    "ActiveWindow",
    "ScreenOCRSource",
    "TypingDynamicsSource",
    "DocumentSource",
    "CalendarSource",
    "WindowsCalendarSource",
    "ObservationWorker",
]
