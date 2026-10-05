"""SHADOW perception layer — sources that observe the user's context."""

from .active_window import ActiveWindow, ActiveWindowSource
from .base import PerceptionSource
from .budget import BudgetController
from .cadence import AdaptiveCadence, CadenceInfo
from .calendar import CalendarSource
from .calendar_winrt import WindowsCalendarSource
from .change_detector import ChangeDetector
from .clipboard import ClipboardSource
from .documents import DocumentSource
from .identifiers import IdentifierExtractor, Identifiers
from .interactive import (
    ElementRole,
    InteractiveElement,
    InteractiveExtractor,
)
from .observer import ObservationWorker
from .screen_ocr import ScreenOCRSource
from .tabs import (
    RelatedTabs,
    StaleTab,
    TabInfo,
    TabReader,
    TabStateTracker,
)
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
    "ElementRole",
    "InteractiveElement",
    "InteractiveExtractor",
    "IdentifierExtractor",
    "Identifiers",
    "RelatedTabs",
    "StaleTab",
    "TabInfo",
    "TabReader",
    "TabStateTracker",
    "ChangeDetector",
    "AdaptiveCadence",
    "CadenceInfo",
]
