"""UIA text extraction — turn a tree into paragraph-level text.

Reads the UIA tree from `uia.py` and produces the actual content the
LLM and vector store consume: headings, paragraphs, list items, and
document text — in reading order.

Skips UI chrome (buttons, menu items, tab labels, icon glyphs) that
would add noise without meaning.
"""

from dataclasses import dataclass

from .uia import UIANode

# Controls whose text is actual content the user is reading/writing.
_CONTENT_TYPES = {
    "TextControl",
    "EditControl",
    "DocumentControl",
    "HeadingControl",
    "ListItemControl",
    "TreeItemControl",
    "HeaderItemControl",
    "HyperlinkControl",
}

# Controls to explicitly skip — chrome, not content.
_CHROME_TYPES = {
    "ButtonControl",
    "MenuItemControl",
    "TabItemControl",
    "ScrollBarControl",
    "ThumbControl",
    "ImageControl",
    "SeparatorControl",
    "StatusBarControl",
    "TitleBarControl",
    "MenuBarControl",
    "ToolBarControl",
}

DEFAULT_MAX_CHARS = 4000
MIN_BLOCK_CHARS = 2


@dataclass
class TextBlock:
    text: str
    control_type: str
    depth: int

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "control_type": self.control_type,
            "depth": self.depth,
        }


class UIATextExtractor:
    """Extracts paragraph-level text from a UIA tree."""

    def __init__(self, max_chars: int = DEFAULT_MAX_CHARS):
        self.max_chars = max_chars
        self._last_text: str = ""

    # ---------- public API ----------

    def extract(self, root: UIANode) -> dict:
        """Return {text, blocks, char_count, truncated} for the tree."""
        self._last_text = ""
        blocks = self._walk(root, depth=0)

        joined = self._join_blocks(blocks)
        truncated = False

        if len(joined) > self.max_chars:
            joined = joined[: self.max_chars].rstrip()
            # Find a natural break for the ellipsis
            truncation_point = max(
                joined.rfind("\n\n"),
                joined.rfind(". "),
                joined.rfind("! "),
                joined.rfind("? "),
            )
            if truncation_point > self.max_chars * 0.7:
                joined = joined[: truncation_point + 1]
            joined = joined.rstrip() + " […]"
            truncated = True

        return {
            "text": joined,
            "blocks": [b.to_dict() for b in blocks],
            "char_count": len(joined),
            "truncated": truncated,
        }

    # ---------- internals ----------

    def _walk(self, node: UIANode | None, depth: int) -> list[TextBlock]:
        if node is None:
            return []

        blocks: list[TextBlock] = []

        if self._should_extract(node):
            block = self._make_block(node, depth)
            if block is not None:
                blocks.append(block)

        for child in node.children:
            blocks.extend(self._walk(child, depth + 1))

        return blocks

    @staticmethod
    def _should_extract(node: UIANode) -> bool:
        if node.is_password:
            return False
        if node.is_offscreen:
            return False
        if node.control_type in _CHROME_TYPES:
            return False
        if node.control_type not in _CONTENT_TYPES:
            return False
        return bool(node.name and node.name.strip())

    def _make_block(self, node: UIANode, depth: int) -> TextBlock | None:
        text = self._clean_text(node.name)
        if not text or len(text) < MIN_BLOCK_CHARS:
            return None

        # Dedupe adjacent identical text (common in list items)
        if text == self._last_text:
            return None
        self._last_text = text

        return TextBlock(
            text=text,
            control_type=node.control_type,
            depth=depth,
        )

    @staticmethod
    def _clean_text(text: str) -> str:
        """Collapse whitespace, strip leading bullets/decoration."""
        text = text.strip()
        # Remove common list decorations that add noise
        for prefix in ("• ", "- ", "* ", "· "):
            if text.startswith(prefix):
                text = text[len(prefix) :].strip()
                break
        # Collapse runs of whitespace
        return " ".join(text.split())

    @staticmethod
    def _join_blocks(blocks: list[TextBlock]) -> str:
        """Join blocks into readable text with paragraph breaks."""
        lines: list[str] = []

        for block in blocks:
            # Insert a blank line between top-level sections
            if block.depth == 0 and lines:
                lines.append("")
            lines.append(block.text)

        return "\n".join(lines).strip()
