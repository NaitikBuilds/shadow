"""SHADOW agent layer — proactive features that act on memory."""

from .ambient import AmbientTask, AmbientTaskList
from .capture import QuickCapture
from .clipboard_actions import ClipboardActionsEngine
from .decay import KnowledgeDecayEngine
from .dnd import DoNotDisturb
from .focus import FocusShield, FocusState
from .focus_patterns import FocusPatternsEngine
from .forecasting import ForecastingEngine
from .insight import Insight
from .intent_notes import IntentNotesEngine
from .prompt_builder import PromptBuilder
from .recovery import RecoveryEngine
from .recurring import RecurringPatternEngine
from .sessions import Session, SessionMemory
from .style import StyleMirrorEngine, StyleResult
from .taint import Taint, TaintedValue, TaintPropagator, max_taint

__all__ = [
    "AmbientTask",
    "AmbientTaskList",
    "ClipboardActionsEngine",
    "DoNotDisturb",
    "FocusPatternsEngine",
    "FocusShield",
    "FocusState",
    "ForecastingEngine",
    "Insight",
    "IntentNotesEngine",
    "KnowledgeDecayEngine",
    "PromptBuilder",
    "QuickCapture",
    "RecoveryEngine",
    "RecurringPatternEngine",
    "Session",
    "SessionMemory",
    "StyleMirrorEngine",
    "StyleResult",
    "Taint",
    "TaintedValue",
    "TaintPropagator",
    "max_taint",
]
