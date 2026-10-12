"""ImageFileSource — caption new image files in watched folders.

Watches configured folders for new image files (PNG / JPG / JPEG /
WEBP) and sends each new file to the vision service for captioning.
Uses the document_parsing consent channel.

Design:
  - Seed on first tick so existing files aren't re-ingested.
  - One file per tick (most recently modified).
  - Reuses downscale + encode logic from ScreenVisionSource.
  - Skips files above max_file_size_mb.
  - Returns None when vision service is unavailable or disabled.
"""

import io
from datetime import datetime
from pathlib import Path
from typing import Any

from .base import PerceptionSource


class ImageFileSource(PerceptionSource):
    """Watches folders for new image files and captions them."""

    name = "image_file"
    channel = "document_parsing"

    def __init__(
        self,
        vision_service,
        watch_folders: list[str],
        extensions: list[str],
        max_file_size_mb: int = 15,
        image_max_side: int = 1024,
    ):
        self.vision_service = vision_service
        self.watch_folders = [
            Path(f).expanduser().resolve() for f in watch_folders if f
        ]
        self.extensions = {
            e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions
        }
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self.image_max_side = image_max_side
        self._seen: dict[str, float] = {}
        self._seeded = False

    # ---------- public API ----------

    def sample(self) -> dict[str, Any] | None:
        if self.vision_service is None:
            return None
        if not self.vision_service.is_available():
            return None
        if not self.watch_folders:
            return None

        if not self._seeded:
            self._seed_seen()
            self._seeded = True
            return None

        candidates = self._find_new_files()
        if not candidates:
            return None

        try:
            path = max(candidates, key=lambda p: p.stat().st_mtime)
        except OSError:
            return None

        caption = self._caption(path)

        try:
            self._seen[str(path)] = path.stat().st_mtime
        except OSError:
            pass

        if not caption:
            return None

        try:
            size_bytes = path.stat().st_size
        except OSError:
            size_bytes = 0

        return {
            "path": str(path),
            "name": path.name,
            "extension": path.suffix.lower(),
            "size_bytes": size_bytes,
            "caption": caption,
            "timestamp": datetime.utcnow().isoformat(sep=" ", timespec="seconds"),
        }

    # ---------- internals ----------

    def _seed_seen(self) -> None:
        for folder in self.watch_folders:
            if not folder.exists():
                continue
            for path in self._iter_candidates(folder):
                try:
                    self._seen[str(path)] = path.stat().st_mtime
                except OSError:
                    continue

    def _find_new_files(self) -> list[Path]:
        candidates: list[Path] = []
        for folder in self.watch_folders:
            if not folder.exists():
                continue
            for path in self._iter_candidates(folder):
                key = str(path)
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    continue
                if self._seen.get(key, 0.0) < mtime:
                    candidates.append(path)
        return candidates

    def _iter_candidates(self, folder: Path):
        try:
            for path in folder.rglob("*"):
                if not path.is_file():
                    continue
                if path.suffix.lower() not in self.extensions:
                    continue
                try:
                    if path.stat().st_size > self.max_file_size_bytes:
                        continue
                except OSError:
                    continue
                yield path
        except PermissionError:
            return

    def _caption(self, path: Path) -> str:
        try:
            raw = path.read_bytes()
        except OSError:
            return ""

        image_bytes = self._downscale_and_encode(raw)
        if not image_bytes:
            return ""

        try:
            return self.vision_service.caption(image_bytes)
        except Exception:
            return ""

    def _downscale_and_encode(self, image_bytes: bytes) -> bytes:
        """Downscale + normalize to PNG. Falls back to original bytes
        if Pillow isn't available."""
        try:
            from PIL import Image
        except ImportError:
            return image_bytes

        try:
            img = Image.open(io.BytesIO(image_bytes))
            img.load()
        except Exception:
            return b""

        try:
            w, h = img.size
            longest = max(w, h)
            if longest > self.image_max_side:
                scale = self.image_max_side / longest
                img = img.resize(
                    (int(w * scale), int(h * scale)),
                    Image.Resampling.LANCZOS,
                )
        except Exception:
            pass

        # If alpha channel is present, keep PNG; else prefer PNG anyway
        # (lossless) with a JPEG fallback if the result is huge.
        try:
            buf = io.BytesIO()
            if img.mode in ("RGBA", "LA"):
                img.save(buf, format="PNG", optimize=True)
            else:
                img.convert("RGB").save(buf, format="PNG", optimize=True)
            return buf.getvalue()
        except Exception:
            try:
                buf = io.BytesIO()
                img.convert("RGB").save(buf, format="JPEG", quality=85)
                return buf.getvalue()
            except Exception:
                return b""

    def stop(self) -> None:
        pass
