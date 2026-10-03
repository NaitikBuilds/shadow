"""UI Automation reader — structured access to the active window.

Reads the Windows UI Automation tree of the currently focused window
and returns a structured payload of elements: text blocks, buttons,
links, inputs, headings. Preferred over OCR when available.

Design notes:
  - Safety-first: depth and element caps prevent runaway traversal.
  - Privacy: password fields are dropped entirely, including children.
  - Graceful degradation: if `uiautomation` isn't installed or COM
    init fails, `sample()` returns None and the observer falls back
    to OCR.
  - No screenshots. No image processing. UIA reads the content model.
"""

# Known limitation: Chromium-based browsers (Chrome, Edge, Brave) only
# expose their page content to UIA when the Windows screen-reader flag
# was set *before* the browser started. Our observer sets the flag on
# startup, but if Chrome is already running, it won't see the change.
# In that case, the UIA tree contains only the browser's chrome (tabs,
# address bar) and the observer's OCR fallback handles page content.
# See _enable_screen_reader_flag() for the flag setter.

import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from .base import PerceptionSource

# Windows SPI_SETSCREENREADER flag. When set, Chromium browsers and
# some other apps enable their full UIA accessibility tree. Cleared
# automatically when the process exits.
_SPI_SETSCREENREADER = 0x0047


def _enable_screen_reader_flag() -> None:
    """Tell Windows a screen reader is active so Chromium apps expose
    their full accessibility tree. Safe to call repeatedly."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.user32.SystemParametersInfoW(_SPI_SETSCREENREADER, True, None, 0)
    except Exception:
        pass


def _disable_screen_reader_flag() -> None:
    """Clear the flag when SHADOW shuts down."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.user32.SystemParametersInfoW(_SPI_SETSCREENREADER, False, None, 0)
    except Exception:
        pass


# Controls whose "name" typically holds meaningful text.
_TEXT_CONTROL_TYPES = {
    "TextControl",
    "EditControl",
    "DocumentControl",
    "HyperlinkControl",
    "ButtonControl",
    "ListItemControl",
    "TreeItemControl",
    "MenuItemControl",
    "TabItemControl",
    "HeaderItemControl",
    "HeadingControl",
}


@dataclass
class UIANode:
    """A single element in the UI Automation tree."""

    name: str
    control_type: str
    automation_id: str = ""
    class_name: str = ""
    is_password: bool = False
    is_enabled: bool = True
    is_offscreen: bool = False
    bounding_rect: tuple[int, int, int, int] = (0, 0, 0, 0)
    children: list["UIANode"] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def is_textual(self) -> bool:
        return bool(self.name) and self.control_type in _TEXT_CONTROL_TYPES


class UIAutomationSource(PerceptionSource):
    """Reads the UIA tree of the active window."""

    name = "screen_uia"
    channel = "screen_capture"

    def __init__(
        self,
        max_depth: int = 8,
        max_elements: int = 500,
        min_useful_nodes: int = 3,
    ):
        self.max_depth = max_depth
        self.max_elements = max_elements
        self.min_useful_nodes = min_useful_nodes
        self._element_count = 0
        self._max_depth_reached = 0

    # ---------- public API ----------

    def sample(self) -> dict[str, Any] | None:
        if sys.platform != "win32":
            return None

        _enable_screen_reader_flag()

        try:
            import uiautomation as auto
        except ImportError:
            return None

        # COM must be initialized per-thread. QThread doesn't do this
        # by default, so we attempt and tolerate failures.
        self._ensure_com()

        root, window_info = self._get_active_root(auto)
        if root is None:
            return None

        self._element_count = 0
        self._max_depth_reached = 0
        try:
            tree = self._walk(root, depth=0)
        except Exception:
            return None

        if tree is None:
            return None

        node_count = self._count_nodes(tree)
        if node_count < self.min_useful_nodes:
            return None

        return {
            "root": tree.to_dict(),
            "node_count": node_count,
            "max_depth_reached": self._max_depth_reached,
            "window_title": window_info.get("title", ""),
            "process": window_info.get("process", ""),
            "timestamp": datetime.utcnow().isoformat(sep=" ", timespec="seconds"),
        }

    # ---------- internals ----------

    @staticmethod
    def _ensure_com() -> None:
        try:
            import comtypes

            comtypes.CoInitialize()
        except Exception:
            pass

    def _get_active_root(self, auto) -> tuple[Any, dict]:
        """Return (root_control, window_info) for the foreground window."""
        try:
            import psutil
            import win32gui
            import win32process
        except ImportError:
            return None, {}

        try:
            hwnd = win32gui.GetForegroundWindow()
        except Exception:
            return None, {}

        if not hwnd:
            return None, {}

        try:
            title = win32gui.GetWindowText(hwnd) or ""
        except Exception:
            title = ""

        process = ""
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid:
                process = psutil.Process(pid).name()
        except Exception:
            pass

        try:
            root = auto.ControlFromHandle(hwnd)
        except Exception:
            return None, {}

        if root is None:
            return None, {}

        return root, {"title": title.strip(), "process": process.strip()}

    def _walk(self, control, depth: int) -> UIANode | None:
        if depth > self.max_depth:
            return None
        if self._element_count >= self.max_elements:
            return None

        self._element_count += 1
        if depth > self._max_depth_reached:
            self._max_depth_reached = depth

        node = self._control_to_node(control)
        if node is None:
            return None

        # Password fields are dropped entirely (no children read either).
        if node.is_password:
            return None

        # Offscreen elements add noise and cost; drop them.
        if node.is_offscreen:
            return None

        # Text controls with empty or icon-only names are visual noise
        # (e.g. Segoe MDL2 icon glyphs in the private-use Unicode range).
        if node.control_type == "TextControl" and self._is_noise_text(node.name):
            return None

        try:
            children = control.GetChildren()
        except Exception:
            children = []

        for child in children:
            if self._element_count >= self.max_elements:
                break
            child_node = self._walk(child, depth + 1)
            if child_node is not None:
                node.children.append(child_node)

        return node

    @staticmethod
    def _is_noise_text(name: str) -> bool:
        """Return True for empty names or icon-font glyphs only."""
        if not name:
            return True
        for ch in name:
            cp = ord(ch)
            if not (0xE000 <= cp <= 0xF8FF):  # private-use area
                return False
        return True

    @staticmethod
    def _control_to_node(control) -> UIANode | None:
        try:
            name = (control.Name or "").strip()
        except Exception:
            name = ""

        try:
            control_type = control.ControlTypeName or ""
        except Exception:
            control_type = ""

        try:
            automation_id = control.AutomationId or ""
        except Exception:
            automation_id = ""

        try:
            class_name = control.ClassName or ""
        except Exception:
            class_name = ""

        try:
            is_password = bool(control.IsPassword)
        except Exception:
            is_password = False

        try:
            is_enabled = bool(control.IsEnabled)
        except Exception:
            is_enabled = True

        try:
            is_offscreen = bool(control.IsOffscreen)
        except Exception:
            is_offscreen = False

        rect = (0, 0, 0, 0)
        try:
            r = control.BoundingRectangle
            rect = (int(r.left), int(r.top), int(r.right), int(r.bottom))
        except Exception:
            pass

        return UIANode(
            name=name,
            control_type=control_type,
            automation_id=automation_id,
            class_name=class_name,
            is_password=is_password,
            is_enabled=is_enabled,
            is_offscreen=is_offscreen,
            bounding_rect=rect,
        )

    @staticmethod
    def _count_nodes(node: UIANode) -> int:
        total = 1
        for child in node.children:
            total += UIAutomationSource._count_nodes(child)
        return total
