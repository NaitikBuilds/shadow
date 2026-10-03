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
from .uia import UIANode, UIAutomationSource
from .uia_text import TextBlock, UIATextExtractor
from .window_classifier import WindowCategory, WindowClassifier, WindowProfile

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
    "UIAutomationSource",
    "UIANode",
    "WindowsCalendarSource",
    "WindowCategory",
    "WindowClassifier",
    "WindowProfile",
    "TextBlock",
    "UIATextExtractor",
]
