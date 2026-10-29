"""SHADOW agent layer — proactive features that act on memory."""

from .ambient import AmbientTask, AmbientTaskList
from .capture import QuickCapture
from .clipboard_actions import ClipboardActionsEngine
from .consent_gate import (
    CHANNEL_NOTIFICATION_SUMMARIZATION,
    CHANNEL_VISION_BACKGROUND,
    DR_P4_09_APPROVED_KEY,
    ConsentDenied,
    ConsentGate,
    register_phase4_consent_channels,
)
from .decay import KnowledgeDecayEngine
from .dnd import DoNotDisturb
from .feedback import FeedbackStats, FeedbackStore
from .focus import FocusShield, FocusState
from .focus_patterns import FocusPatternsEngine
from .forecasting import ForecastingEngine
from .insight import Insight
from .intent_notes import IntentNotesEngine
from .prompt_builder import PromptBuilder
from .recovery import RecoveryEngine
from .recurring import RecurringPatternEngine
from .sessions import Session, SessionMemory
from .stuck import StuckDetector
from .style import StyleMirrorEngine, StyleResult
from .taint import Taint, TaintedValue, TaintPropagator, max_taint
from .vision_intents import (
    VisionIntent,
    build_combined_context,
    build_vision_context,
    detect_intent,
    wants_memory_context,
)
from .vision_offer import (
    THIN_TEXT_THRESHOLD_CHARS,
    VISUAL_CATEGORIES,
    VisionOfferPolicy,
)

__all__ = [
    "AmbientTask",
    "AmbientTaskList",
    "ClipboardActionsEngine",
    "DoNotDisturb",
    "FeedbackStats",
    "FeedbackStore",
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
    "StuckDetector",
    "THIN_TEXT_THRESHOLD_CHARS",
    "VISUAL_CATEGORIES",
    "VisionOfferPolicy",
    "VisionIntent",
    "build_vision_context",
    "build_combined_context",
    "detect_intent",
    "wants_memory_context",
    "CHANNEL_NOTIFICATION_SUMMARIZATION",
    "CHANNEL_VISION_BACKGROUND",
    "DR_P4_09_APPROVED_KEY",
    "ConsentDenied",
    "ConsentGate",
    "register_phase4_consent_channels",
]
