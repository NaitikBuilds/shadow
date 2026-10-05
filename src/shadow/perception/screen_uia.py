"""Screen UIA source — structured reading of the active window.

Integrates WindowClassifier, UIAutomationSource, UIATextExtractor,
and IdentifierExtractor to produce one observation per tick with:
  - Clean structured text from the UIA tree
  - URLs and file paths as identifiers
  - Window title and process

Falls back silently if UIA is unavailable or the window category
doesn't support it.
"""

import sys
from datetime import datetime
from typing import Any

from .active_window import ActiveWindowSource
from .base import PerceptionSource
from .identifiers import IdentifierExtractor
from .uia import UIANode, UIAutomationSource
from .uia_text import UIATextExtractor
from .window_classifier import WindowClassifier


class ScreenUIASource(PerceptionSource):
    """Reads the UIA tree of the active window and extracts content."""

    name = "screen_uia"
    channel = "screen_capture"
    is_screen_source = True

    def __init__(
        self,
        classifier: WindowClassifier | None = None,
        max_elements: int = 500,
        max_text_chars: int = 4000,
    ):
        self.classifier = classifier or WindowClassifier()
        self.uia = UIAutomationSource(max_elements=max_elements)
        self.text_extractor = UIATextExtractor(max_chars=max_text_chars)
        self.identifier_extractor = IdentifierExtractor(self.classifier)

    def sample(self) -> dict[str, Any] | None:
        if sys.platform != "win32":
            return None

        window = self._active_window()
        if not window:
            return None

        profile = self.classifier.classify(
            process=window.get("process", ""),
            title=window.get("title", ""),
        )

        if profile.is_self:
            return None
        if not profile.use_uia:
            return None

        payload = self.uia.sample()
        if payload is None:
            return None

        root = self._rebuild_tree(payload.get("root"))
        if root is None:
            return None

        text_result = self.text_extractor.extract(root)
        text = text_result.get("text", "").strip()

        identifiers = self.identifier_extractor.extract(
            process=window.get("process", ""),
            title=window.get("title", ""),
            root=root,
            category=profile.category,
        )

        # Skip if there's nothing useful to record
        if not text and identifiers.is_empty():
            return None

        return {
            "text": text,
            "window_title": window.get("title", ""),
            "process": window.get("process", ""),
            "category": profile.category.value,
            "urls": identifiers.urls,
            "paths": identifiers.paths,
            "primary_url": identifiers.primary_url,
            "primary_path": identifiers.primary_path,
            "truncated": text_result.get("truncated", False),
            "char_count": text_result.get("char_count", 0),
            "timestamp": datetime.utcnow().isoformat(sep=" ", timespec="seconds"),
        }

    # ---------- internals ----------

    @staticmethod
    def _active_window() -> dict | None:
        try:
            return ActiveWindowSource().sample()
        except Exception:
            return None

    @staticmethod
    def _rebuild_tree(data: dict | None) -> UIANode | None:
        if not data:
            return None

        def from_dict(d):
            return UIANode(
                name=d.get("name", ""),
                control_type=d.get("control_type", ""),
                automation_id=d.get("automation_id", ""),
                class_name=d.get("class_name", ""),
                value=d.get("value", ""),
                is_password=d.get("is_password", False),
                is_enabled=d.get("is_enabled", True),
                is_selected=d.get("is_selected", False),
                is_offscreen=d.get("is_offscreen", False),
                bounding_rect=tuple(d.get("bounding_rect", (0, 0, 0, 0))),
                children=[from_dict(c) for c in d.get("children", [])],
            )

        try:
            return from_dict(data)
        except Exception:
            return None
