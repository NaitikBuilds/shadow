"""Image observation schema and retrieval helpers.

Image observations live in the standard observations table with
`source` in {image_file, screen_vision, region_capture}. The content
column holds human-readable text (e.g. "Image: name\\n<caption>"), and
the metadata column holds the structured payload as JSON.

This module provides typed access so callers never need to parse JSON
or know the exact content format.
"""

import json
from dataclasses import dataclass

# All source values that represent a vision-derived observation.
IMAGE_SOURCES = ("image_file", "screen_vision", "region_capture")


@dataclass
class ImageObservation:
    id: int
    timestamp: str
    source: str
    name: str
    caption: str
    path: str = ""
    extension: str = ""
    size_bytes: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "source": self.source,
            "name": self.name,
            "caption": self.caption,
            "path": self.path,
            "extension": self.extension,
            "size_bytes": self.size_bytes,
        }


class ImageObservationStore:
    """Read and write access to image observations."""

    def __init__(self, memory):
        self.memory = memory

    # ---------- queries ----------

    def recent(self, limit: int = 20) -> list[ImageObservation]:
        placeholders = ",".join("?" * len(IMAGE_SOURCES))
        cur = self.memory.conn.cursor()
        cur.execute(
            f"SELECT id, timestamp, source, content, metadata "
            f"FROM observations WHERE source IN ({placeholders}) "
            f"ORDER BY timestamp DESC LIMIT ?",
            (*IMAGE_SOURCES, limit),
        )
        return [self._row_to_observation(row) for row in cur.fetchall()]

    def between(self, start: str, end: str) -> list[ImageObservation]:
        placeholders = ",".join("?" * len(IMAGE_SOURCES))
        cur = self.memory.conn.cursor()
        cur.execute(
            f"SELECT id, timestamp, source, content, metadata "
            f"FROM observations "
            f"WHERE source IN ({placeholders}) "
            f"AND timestamp BETWEEN ? AND ? "
            f"ORDER BY timestamp ASC",
            (*IMAGE_SOURCES, start, end),
        )
        return [self._row_to_observation(row) for row in cur.fetchall()]

    def count(self) -> int:
        placeholders = ",".join("?" * len(IMAGE_SOURCES))
        cur = self.memory.conn.cursor()
        cur.execute(
            f"SELECT COUNT(*) FROM observations " f"WHERE source IN ({placeholders})",
            IMAGE_SOURCES,
        )
        return int(cur.fetchone()[0] or 0)

    def by_extension(self, ext: str) -> list[ImageObservation]:
        ext = ext.lower()
        if not ext.startswith("."):
            ext = "." + ext
        cur = self.memory.conn.cursor()
        cur.execute(
            "SELECT id, timestamp, source, content, metadata "
            "FROM observations "
            "WHERE source = 'image_file' "
            "AND metadata LIKE ? "
            "ORDER BY timestamp DESC",
            (f'%"extension": "{ext}"%',),
        )
        return [self._row_to_observation(row) for row in cur.fetchall()]

    def search_captions(self, keyword: str, limit: int = 20) -> list[ImageObservation]:
        if not keyword:
            return []
        placeholders = ",".join("?" * len(IMAGE_SOURCES))
        cur = self.memory.conn.cursor()
        cur.execute(
            f"SELECT id, timestamp, source, content, metadata "
            f"FROM observations "
            f"WHERE source IN ({placeholders}) "
            f"AND content LIKE ? "
            f"ORDER BY timestamp DESC LIMIT ?",
            (*IMAGE_SOURCES, f"%{keyword}%", limit),
        )
        return [self._row_to_observation(row) for row in cur.fetchall()]

    # ---------- writes ----------

    def record_screen_vision(
        self,
        text: str,
        window_title: str = "",
        process: str = "",
        task: str = "caption",
    ) -> int | None:
        """Persist a screen vision result as an observation.

        Returns the observation id or None on failure.
        """
        text = (text or "").strip()
        if not text:
            return None

        payload = {
            "text": text,
            "task": task,
            "window_title": window_title,
            "process": process,
        }
        content = text
        try:
            obs_id = self.memory.add_observation(
                "screen_vision",
                content,
                metadata=json.dumps(payload, default=str),
            )
        except Exception:
            return None
        return obs_id

    # ---------- internals ----------

    def _row_to_observation(self, row: tuple) -> ImageObservation:
        obs_id, ts, source, content, metadata = row
        parsed = self._parse_metadata(metadata)
        caption = (
            parsed.get("caption")
            or parsed.get("text")
            or self._extract_caption(content)
        )
        name = parsed.get("name") or self._extract_name(content, source)
        return ImageObservation(
            id=obs_id,
            timestamp=ts,
            source=source,
            name=name,
            caption=caption,
            path=str(parsed.get("path", "")),
            extension=str(parsed.get("extension", "")),
            size_bytes=int(parsed.get("size_bytes", 0) or 0),
        )

    @staticmethod
    def _parse_metadata(metadata) -> dict:
        if not metadata:
            return {}
        try:
            data = json.loads(metadata)
            return data if isinstance(data, dict) else {}
        except (TypeError, ValueError):
            return {}

    @staticmethod
    def _extract_caption(content: str) -> str:
        text = (content or "").strip()
        if not text:
            return ""
        # Formats we produce:
        #   "Image: name.png\n<caption>"
        #   "<caption>"  (screen_vision)
        #   "Window: x\nURL: y\n\n<caption>"  (future region_capture)
        nl2 = text.find("\n\n")
        if nl2 >= 0:
            return text[nl2 + 2 :].strip()
        first_nl = text.find("\n")
        if first_nl >= 0:
            return text[first_nl + 1 :].strip()
        return text

    @staticmethod
    def _extract_name(content: str, source: str) -> str:
        if source != "image_file":
            return ""
        text = (content or "").strip()
        first_line = text.split("\n", 1)[0].strip()
        prefix = "Image: "
        if first_line.startswith(prefix):
            return first_line[len(prefix) :].strip()
        return ""
