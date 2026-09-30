"""SHADOW agent layer — proactive features that act on memory."""

from .ambient import AmbientTask, AmbientTaskList
from .capture import QuickCapture
from .clipboard_actions import ClipboardActionsEngine
from .decay import KnowledgeDecayEngine
from .focus import FocusShield, FocusState
from .forecasting import ForecastingEngine
from .insight import Insight
from .prompt_builder import PromptBuilder
from .recovery import RecoveryEngine
from .sessions import Session, SessionMemory
from .style import StyleMirrorEngine, StyleResult
from .taint import Taint, TaintedValue, TaintPropagator, max_taint

__all__ = [
    "AmbientTask",
    "AmbientTaskList",
    "ClipboardActionsEngine",
    "FocusShield",
    "FocusState",
    "ForecastingEngine",
    "Insight",
    "KnowledgeDecayEngine",
    "PromptBuilder",
    "QuickCapture",
    "RecoveryEngine",
    "Session",
    "SessionMemory",
    "StyleMirrorEngine",
    "StyleResult",
    "Taint",
    "TaintedValue",
    "TaintPropagator",
    "max_taint",
]
