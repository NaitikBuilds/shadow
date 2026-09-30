"""SHADOW agent layer — proactive features that act on memory."""

from .clipboard_actions import ClipboardActionsEngine
from .decay import KnowledgeDecayEngine
from .focus import FocusShield, FocusState
from .forecasting import ForecastingEngine
from .insight import Insight
from .prompt_builder import PromptBuilder
from .recovery import RecoveryEngine
from .style import StyleMirrorEngine, StyleResult
from .taint import Taint, TaintedValue, TaintPropagator, max_taint

__all__ = [
    "ClipboardActionsEngine",
    "FocusShield",
    "FocusState",
    "ForecastingEngine",
    "Insight",
    "KnowledgeDecayEngine",
    "PromptBuilder",
    "RecoveryEngine",
    "StyleMirrorEngine",
    "StyleResult",
    "Taint",
    "TaintedValue",
    "TaintPropagator",
    "max_taint",
]
