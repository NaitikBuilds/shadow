"""SHADOW perception layer — sources that observe the user's context."""

from .base import PerceptionSource
from .active_window import ActiveWindowSource, ActiveWindow
from .screen_ocr import ScreenOCRSource
from .typing import TypingDynamicsSource
from .documents import DocumentSource
from .calendar import CalendarSource
from .calendar_winrt import WindowsCalendarSource
from .observer import ObservationWorker

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
