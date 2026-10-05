"""Reading Position Memory — remember where you were in long documents.

Reads the active window's scroll bar and nearest heading to record
a reading position. Enables future "resume reading" insights:
"You were reading about pathlib — resume at 62%?"

Only updates when position changes by >= min_change_pct to avoid
noise. Positions older than retention_days are pruned.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from .identifiers import IdentifierExtractor
from .uia import UIANode


@dataclass
class ReadingPosition:
    identifier: str
    title: str
    position_pct: float
    section: str
    updated_at: str


class ReadingPositionReader:
    """Extracts reading position from a UIA tree."""

    def extract(self, root: UIANode | None) -> tuple[float, str]:
        """Return (position_pct, current_section).

        position_pct is 0.0-100.0 based on the vertical scroll bar.
        current_section is the nearest preceding heading text.
        """
        if root is None:
            return 0.0, ""

        scrollbar = self._find_vertical_scrollbar(root)
        pct = 0.0
        if scrollbar is not None:
            pct = self._compute_pct(scrollbar)

        section = self._find_nearest_heading(root)
        return pct, section

    # ---------- scroll bar ----------

    def _find_vertical_scrollbar(self, node: UIANode | None) -> UIANode | None:
        if node is None:
            return None
        if node.control_type == "ScrollBarControl":
            if "vertical" in (node.name or "").lower():
                return node
        for child in node.children:
            found = self._find_vertical_scrollbar(child)
            if found is not None:
                return found
        return None

    @staticmethod
    def _compute_pct(scrollbar: UIANode) -> float:
        """Read scroll position from value and max in the node's value."""
        # value is stored as "value|max" by the observer in a special case.
        # Fall back to 0 if we can't parse.
        if not scrollbar.value:
            return 0.0
        try:
            parts = scrollbar.value.split("|")
            if len(parts) != 2:
                return 0.0
            value = float(parts[0])
            maximum = float(parts[1])
            if maximum <= 0:
                return 0.0
            return max(0.0, min(100.0, (value / maximum) * 100.0))
        except (ValueError, TypeError):
            return 0.0

    # ---------- section ----------

    def _find_nearest_heading(self, node: UIANode | None) -> str:
        """Return the last heading seen in reading order."""
        headings: list[str] = []
        self._collect_headings(node, headings)
        if not headings:
            return ""
        return headings[-1][:120]

    def _collect_headings(self, node: UIANode | None, out: list[str]) -> None:
        if node is None:
            return
        if node.control_type == "HeadingControl" and node.name:
            out.append(node.name.strip())
        for child in node.children:
            self._collect_headings(child, out)


class ReadingPositionTracker:
    """Persists reading positions and queries recent ones."""

    def __init__(self, memory, config):
        self.memory = memory
        cfg = (config.get("perception") or {}).get("reading_position") or {}
        self.enabled = bool(cfg.get("enabled", True))
        self.min_change_pct = float(cfg.get("min_change_pct", 5))
        self.retention_days = int(cfg.get("retention_days", 30))
        self.extractor = IdentifierExtractor()

    # ---------- persistence ----------

    def record(
        self,
        process: str,
        title: str,
        root: UIANode | None,
    ) -> ReadingPosition | None:
        """Read position from tree and persist if meaningfully different."""
        if not self.enabled:
            return None

        identifiers = self.extractor.extract(process=process, title=title, root=root)
        identifier = identifiers.primary_url or identifiers.primary_path
        if not identifier:
            return None

        reader = ReadingPositionReader()
        pct, section = reader.extract(root)
        if pct == 0.0 and not section:
            return None

        # Check current stored value
        existing = self.get(identifier)
        if existing is not None:
            if abs(existing.position_pct - pct) < self.min_change_pct:
                return existing

        now = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
        with self.memory._lock:
            cur = self.memory.conn.cursor()
            cur.execute(
                """
                INSERT INTO reading_positions
                    (identifier, title, position_pct, section, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(identifier) DO UPDATE SET
                    title = excluded.title,
                    position_pct = excluded.position_pct,
                    section = excluded.section,
                    updated_at = excluded.updated_at
                """,
                (identifier, title[:200], pct, section, now),
            )
            self.memory.conn.commit()

        return ReadingPosition(
            identifier=identifier,
            title=title,
            position_pct=pct,
            section=section,
            updated_at=now,
        )

    # ---------- queries ----------

    def get(self, identifier: str) -> ReadingPosition | None:
        try:
            cur = self.memory.conn.cursor()
            cur.execute(
                "SELECT identifier, title, position_pct, section, updated_at "
                "FROM reading_positions WHERE identifier = ?",
                (identifier,),
            )
            row = cur.fetchone()
        except Exception:
            return None
        if not row:
            return None
        return ReadingPosition(
            identifier=row[0],
            title=row[1],
            position_pct=row[2],
            section=row[3],
            updated_at=row[4],
        )

    def recent(self, limit: int = 10) -> list[ReadingPosition]:
        """Return recently-read documents, most recent first."""
        try:
            cur = self.memory.conn.cursor()
            cur.execute(
                "SELECT identifier, title, position_pct, section, updated_at "
                "FROM reading_positions ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            )
            rows = cur.fetchall()
        except Exception:
            return []
        return [
            ReadingPosition(
                identifier=r[0],
                title=r[1],
                position_pct=r[2],
                section=r[3],
                updated_at=r[4],
            )
            for r in rows
        ]

    def resume_suggestion(self, identifier: str) -> str | None:
        """Return a one-line resume hint for the given document."""
        pos = self.get(identifier)
        if pos is None:
            return None
        section = f' at "{pos.section}"' if pos.section else ""
        return (
            f"You were reading {pos.title[:60]}{section} "
            f"({pos.position_pct:.0f}% through)."
        )

    def prune_old(self) -> int:
        cutoff = (datetime.utcnow() - timedelta(days=self.retention_days)).isoformat(
            sep=" ", timespec="seconds"
        )
        with self.memory._lock:
            cur = self.memory.conn.cursor()
            cur.execute(
                "DELETE FROM reading_positions WHERE updated_at < ?",
                (cutoff,),
            )
            deleted = cur.rowcount
            self.memory.conn.commit()
        return deleted
