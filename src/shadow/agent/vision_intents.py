"""Vision intent routing — detect visual queries in chat.

Deterministic keyword-based detection. When a query requests a visual
analysis ("describe this", "what am I looking at", "explain this error"),
the router selects the appropriate vision task and prompt template.
"""

import re
from dataclasses import dataclass

from shadow.hal.base import (
    TASK_CAPTION,
    TASK_OCR,
    TASK_QUERY,
)


@dataclass
class VisionIntent:
    kind: str
    task: str
    prompt: str
    matched_phrase: str

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "task": self.task,
            "prompt": self.prompt,
            "matched_phrase": self.matched_phrase,
        }


# Trigger patterns, ordered by specificity (longest match wins).
# Each entry: (kind, task, prompt, regex)
_TRIGGERS: list[tuple[str, str, str, re.Pattern]] = [
    (
        "describe_screen",
        TASK_CAPTION,
        "",
        re.compile(
            r"\b(?:what(?:'s| is) (?:on|showing on) (?:my|the) screen"
            r"|what am i (?:looking at|seeing)"
            r"|describe (?:this|the screen|my screen|what i(?:'m| am) (?:looking at|seeing))"
            r"|what(?:'s| is) this)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "explain_error",
        TASK_QUERY,
        "Explain the error visible in this image and suggest a fix.",
        re.compile(
            r"\b(?:explain (?:this|the) error"
            r"|what does (?:this|the) error mean"
            r"|what(?:'s| is) wrong (?:here|with this)"
            r"|help me (?:fix|debug) (?:this|the) error"
            r"|why (?:is|does) this (?:fail|error))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "summarize_page",
        TASK_QUERY,
        "Summarize the main content visible in this image.",
        re.compile(
            r"\b(?:summarize (?:this|the) page"
            r"|summarize what i(?:'m| am) reading"
            r"|what(?:'s| is) this page about"
            r"|give me the gist (?:of this|of the page))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "extract_text",
        TASK_OCR,
        "",
        re.compile(
            r"\b(?:read (?:this|the screen|what i(?:'m| am) looking at)"
            r"|what does (?:this|it) say"
            r"|extract (?:the )?text"
            r"|copy the text (?:from|on) (?:this|the screen))\b",
            re.IGNORECASE,
        ),
    ),
]


def detect_intent(query: str) -> VisionIntent | None:
    """Return a VisionIntent if the query asks for visual analysis."""
    if not query:
        return None
    text = query.strip()
    if not text:
        return None

    for kind, task, prompt, pattern in _TRIGGERS:
        match = pattern.search(text)
        if match:
            return VisionIntent(
                kind=kind,
                task=task,
                prompt=prompt,
                matched_phrase=match.group(0),
            )
    return None


def build_vision_context(intent: VisionIntent, vision_result: dict | None) -> str:
    """Build the context block injected into the LLM prompt.

    vision_result is a ScreenVisionSource payload or None.
    """
    if vision_result is None:
        return (
            f"[Vision requested for {intent.kind} but no image was "
            f"available. Answer the user's question using their memory "
            f"and available context.]"
        )

    text = (vision_result.get("text") or "").strip()
    window = (vision_result.get("window_title") or "").strip()
    process = (vision_result.get("process") or "").strip()

    lines = ["[Vision analysis of the user's active window]"]
    if window or process:
        source = f"{process} — {window}" if process else window
        lines.append(f"Window: {source}")
    lines.append("")
    lines.append(text or "(empty)")
    return "\n".join(lines)


# Keywords that indicate the query also wants memory context.
_MEMORY_KEYWORDS = (
    "yesterday",
    "last week",
    "last month",
    "earlier",
    "before",
    "remind",
    "what did i",
    "previously",
    "related to",
    "how does this",
    "how does that",
    "connection",
)


def wants_memory_context(query: str) -> bool:
    """Return True if the query also asks about past context."""
    if not query:
        return False
    lower = query.lower()
    return any(kw in lower for kw in _MEMORY_KEYWORDS)


def build_combined_context(
    vision_context: str,
    memory_context: str,
) -> str:
    """Merge vision and memory context into one block."""
    parts: list[str] = []
    if vision_context:
        parts.append(vision_context)
    if memory_context:
        parts.append(memory_context)
    return "\n\n".join(parts).strip()
