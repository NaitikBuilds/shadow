"""Interactive element extraction — what the user can act on.

Reads the UIA tree and returns actionable elements: buttons, links,
inputs, tabs, list items, sliders. Each carries a role, label, enabled
state, and bounding rect.

Design notes:
  - Disabled elements are excluded; they can't be acted on.
  - Icon-only buttons (no label) are excluded; they're not useful.
  - Password fields are excluded.
  - Capped at max_elements so dense UIs don't blow up the payload.
"""

from dataclasses import dataclass
from enum import StrEnum

from .uia import UIANode


class ElementRole(StrEnum):
    ACTION = "action"
    INPUT = "input"
    LINK = "link"
    NAVIGATION = "navigation"
    SELECTION = "selection"


# Control type → role. Types not listed here are not interactive.
_ROLE_MAP: dict[str, ElementRole] = {
    # Actions
    "ButtonControl": ElementRole.ACTION,
    "SplitButtonControl": ElementRole.ACTION,
    "MenuItemControl": ElementRole.ACTION,
    # Inputs
    "EditControl": ElementRole.INPUT,
    "ComboBoxControl": ElementRole.INPUT,
    "CheckBoxControl": ElementRole.INPUT,
    "RadioButtonControl": ElementRole.INPUT,
    # Links
    "HyperlinkControl": ElementRole.LINK,
    # Navigation
    "TabItemControl": ElementRole.NAVIGATION,
    "TreeItemControl": ElementRole.NAVIGATION,
    "ListItemControl": ElementRole.NAVIGATION,
    # Selection
    "SliderControl": ElementRole.SELECTION,
    "SpinnerControl": ElementRole.SELECTION,
}

DEFAULT_MAX_ELEMENTS = 100


@dataclass
class InteractiveElement:
    label: str
    role: ElementRole
    control_type: str
    automation_id: str = ""
    class_name: str = ""
    is_enabled: bool = True
    bounding_rect: tuple[int, int, int, int] = (0, 0, 0, 0)
    depth: int = 0

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "role": self.role.value,
            "control_type": self.control_type,
            "automation_id": self.automation_id,
            "class_name": self.class_name,
            "is_enabled": self.is_enabled,
            "bounding_rect": list(self.bounding_rect),
            "depth": self.depth,
        }


class InteractiveExtractor:
    """Extracts interactive elements from a UIA tree."""

    def __init__(self, max_elements: int = DEFAULT_MAX_ELEMENTS):
        self.max_elements = max_elements
        self._count = 0

    def extract(self, root: UIANode) -> dict:
        """Return {elements: [...], count, by_role: {role: count}}."""
        self._count = 0
        elements: list[InteractiveElement] = []
        self._walk(root, depth=0, out=elements)

        by_role: dict[str, int] = {}
        for el in elements:
            by_role[el.role.value] = by_role.get(el.role.value, 0) + 1

        return {
            "elements": [e.to_dict() for e in elements],
            "count": len(elements),
            "by_role": by_role,
        }

    # ---------- internals ----------

    def _walk(
        self,
        node: UIANode | None,
        depth: int,
        out: list[InteractiveElement],
    ) -> None:
        if node is None:
            return
        if self._count >= self.max_elements:
            return

        element = self._to_element(node, depth)
        if element is not None:
            out.append(element)
            self._count += 1

        for child in node.children:
            if self._count >= self.max_elements:
                break
            self._walk(child, depth + 1, out)

    def _to_element(self, node: UIANode, depth: int) -> InteractiveElement | None:
        role = _ROLE_MAP.get(node.control_type)
        if role is None:
            return None

        # Password fields — never expose as interactive
        if node.is_password:
            return None

        # Disabled elements can't be acted on
        if not node.is_enabled:
            return None

        # Icon-only buttons (empty label) carry no useful signal
        label = (node.name or "").strip()
        if not label:
            return None

        return InteractiveElement(
            label=label[:120],  # cap label length
            role=role,
            control_type=node.control_type,
            automation_id=node.automation_id,
            class_name=node.class_name,
            is_enabled=node.is_enabled,
            bounding_rect=node.bounding_rect,
            depth=depth,
        )
