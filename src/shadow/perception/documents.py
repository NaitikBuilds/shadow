from datetime import datetime
from pathlib import Path
from typing import Any

from .base import PerceptionSource


class DocumentSource(PerceptionSource):
    """Watches configured folders for recently modified documents.

    On first sample(), seeds the internal "seen" map with every file
    currently in the watch folders, so historical files are not ingested.
    After that, ingests at most one file per tick — the most recently
    modified candidate.
    """

    name = "document"
    channel = "document_parsing"

    def __init__(
        self,
        watch_folders: list[str],
        extensions: list[str],
        max_file_size_mb: int = 5,
        max_chars: int = 4000,
    ):
        self.watch_folders = [
            Path(f).expanduser().resolve() for f in watch_folders if f
        ]
        self.extensions = {
            e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions
        }
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self.max_chars = max_chars
        self._seen: dict[str, float] = {}
        self._seeded = False

    def sample(self) -> dict[str, Any] | None:
        if not self.watch_folders:
            return None

        if not self._seeded:
            self._seed_seen()
            self._seeded = True
            return None

        candidates = self._find_new_files()
        if not candidates:
            return None

        # Most recently modified first
        try:
            path = max(candidates, key=lambda p: p.stat().st_mtime)
        except OSError:
            return None

        text = self._extract(path)
        try:
            self._seen[str(path)] = path.stat().st_mtime
        except OSError:
            pass

        if not text or len(text.strip()) < 50:
            return None

        text = text.strip()[: self.max_chars]
        return {
            "path": str(path),
            "name": path.name,
            "extension": path.suffix.lower(),
            "char_count": len(text),
            "text": text,
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

    def _extract(self, path: Path) -> str:
        ext = path.suffix.lower()
        try:
            if ext in (".txt", ".md"):
                return path.read_text(encoding="utf-8", errors="ignore")
            if ext == ".pdf":
                return self._extract_pdf(path)
            if ext == ".docx":
                return self._extract_docx(path)
        except Exception:
            return ""
        return ""

    def _extract_pdf(self, path: Path) -> str:
        try:
            from pypdf import PdfReader
        except ImportError:
            return ""
        reader = PdfReader(str(path))
        parts: list[str] = []
        total = 0
        for page in reader.pages:
            try:
                text = page.extract_text() or ""
            except Exception:
                continue
            parts.append(text)
            total += len(text)
            if total >= self.max_chars:
                break
        return "\n".join(parts)

    def _extract_docx(self, path: Path) -> str:
        try:
            from docx import Document
        except ImportError:
            return ""
        doc = Document(str(path))
        parts: list[str] = []
        total = 0
        for para in doc.paragraphs:
            text = para.text or ""
            parts.append(text)
            total += len(text)
            if total >= self.max_chars:
                break
        return "\n".join(parts)
