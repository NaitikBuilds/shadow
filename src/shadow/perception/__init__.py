"""SHADOW perception layer — sources that observe the user's context."""

from .active_window import ActiveWindow, ActiveWindowSource
from .base import PerceptionSource
from .budget import BudgetController
from .calendar import CalendarSource
from .calendar_winrt import WindowsCalendarSource
from .clipboard import ClipboardSource
from .documents import DocumentSource
from .observer import ObservationWorker
from .screen_ocr import ScreenOCRSource
from .typing import TypingDynamicsSource

__all__ = [
    "ActiveWindow",
    "ActiveWindowSource",
    "BudgetController",
    "CalendarSource",
    "ClipboardSource",
    "DocumentSource",
    "ObservationWorker",
    "PerceptionSource",
    "ScreenOCRSource",
    "TypingDynamicsSource",
    "WindowsCalendarSource",
]
