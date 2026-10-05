"""URL and file path detection from window content.

Extracts precise identifiers from a window's title and UIA tree:
  - URLs from browsers (title, address bar, page text)
  - File paths from editors (title, breadcrumbs, status bar)

These identifiers become observations' metadata so insights can
reference them by name instead of fuzzy text matching.
"""

import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urlparse

from .uia import UIANode
from .window_classifier import WindowCategory, WindowClassifier

# Regexes
_URL_RE = re.compile(
    r"https?://[A-Za-z0-9.\-]+(?::\d+)?(?:/[^\s]*)?",
    re.IGNORECASE,
)
_FILE_URI_RE = re.compile(r"file:///[^\s]+", re.IGNORECASE)

# Path candidates: /home/user/..., C:\Users\..., ./relative/path
_WINDOWS_PATH_RE = re.compile(r"\b([A-Za-z]:\\[^\s:*?\"<>|]+\.[A-Za-z0-9]{1,8})\b")
_UNIX_PATH_RE = re.compile(r"(?<![\w])(/(?:[\w\-\.]+/)*[\w\-\.]+\.[A-Za-z0-9]{1,8})\b")
_RELATIVE_PATH_RE = re.compile(r"\b([\w\-]+(?:/[\w\-]+)*\.[A-Za-z0-9]{1,8})\b")


@dataclass
class Identifiers:
    urls: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)

    @property
    def primary_url(self) -> str | None:
        return self.urls[0] if self.urls else None

    @property
    def primary_path(self) -> str | None:
        return self.paths[0] if self.paths else None

    def to_dict(self) -> dict:
        return {
            "urls": list(self.urls),
            "paths": list(self.paths),
            "primary_url": self.primary_url,
            "primary_path": self.primary_path,
        }

    def is_empty(self) -> bool:
        return not self.urls and not self.paths


class IdentifierExtractor:
    """Extracts URLs and file paths from a window."""

    # Cap so a badly-behaved app can't spam us
    MAX_URLS = 5
    MAX_PATHS = 5

    def __init__(self, classifier: WindowClassifier | None = None):
        self.classifier = classifier or WindowClassifier()

    # ---------- public API ----------

    def extract(
        self,
        process: str,
        title: str,
        root: UIANode | None = None,
        category: WindowCategory | None = None,
    ) -> Identifiers:
        """Extract URLs and paths from a window."""
        if category is None:
            profile = self.classifier.classify(process, title)
            category = profile.category

        urls: list[str] = []
        paths: list[str] = []

        if category == WindowCategory.BROWSER:
            urls = self._extract_urls(title, root)

        if category == WindowCategory.EDITOR:
            paths = self._extract_paths(title, root)

        # Also try both when the category is OTHER — user may be in an
        # unusual app that still has a URL or path in the title.
        if category == WindowCategory.OTHER:
            urls = self._extract_urls(title, root)
            paths = self._extract_paths(title, root)

        return Identifiers(urls=urls, paths=paths)

    # ---------- URL extraction ----------

    def _extract_urls(self, title: str, root: UIANode | None) -> list[str]:
        candidates: list[str] = []

        # 1. From title
        candidates.extend(self._find_urls_in_text(title))

        # 2. From UIA tree (address bar and page text)
        if root is not None:
            candidates.extend(self._find_urls_in_tree(root))

        return self._dedupe_urls(candidates)[: self.MAX_URLS]

    def _find_urls_in_text(self, text: str) -> list[str]:
        if not text:
            return []
        return [m.group(0) for m in _URL_RE.finditer(text)]

    def _find_urls_in_tree(self, node: UIANode | None) -> list[str]:
        if node is None:
            return []
        results: list[str] = []
        # Check both name and value — address bars store URLs in value
        for text in (node.name, getattr(node, "value", "")):
            if text:
                results.extend(self._find_urls_in_text(text))
        for child in node.children:
            results.extend(self._find_urls_in_tree(child))
        return results

    def _dedupe_urls(self, urls: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for url in urls:
            normalized = self._normalize_url(url)
            if normalized is None:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result

    @staticmethod
    def _normalize_url(url: str) -> str | None:
        url = url.strip().rstrip(".,;:!?)")
        try:
            parsed = urlparse(url)
        except Exception:
            return None
        if not parsed.scheme or not parsed.netloc:
            return None
        # Strip tracking params that add noise
        if not parsed.query:
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        return url

    # ---------- path extraction ----------

    def _extract_paths(self, title: str, root: UIANode | None) -> list[str]:
        candidates: list[str] = []

        # 1. From title — editors put filename first
        candidates.extend(self._find_paths_in_title(title))

        # 2. From UIA tree (breadcrumbs, status bar, tab tooltips)
        if root is not None:
            candidates.extend(self._find_paths_in_tree(root))

        return self._dedupe_paths(candidates)[: self.MAX_PATHS]

    @staticmethod
    def _find_paths_in_title(title: str) -> list[str]:
        if not title:
            return []
        # Editors use "—" or " - " to separate filename from context
        head = title.split("—")[0].split(" - ")[0].strip()
        results: list[str] = []
        results.extend(m.group(0) for m in _WINDOWS_PATH_RE.finditer(head))
        results.extend(m.group(0) for m in _UNIX_PATH_RE.finditer(head))
        if not results:
            # Fall back to relative path like "recovery.py"
            results.extend(m.group(0) for m in _RELATIVE_PATH_RE.finditer(head))
        return results

    def _find_paths_in_tree(self, node: UIANode | None) -> list[str]:
        if node is None:
            return []
        results: list[str] = []
        # Breadcrumbs often show full or partial paths
        if node.name:
            text = node.name
            if "\\" in text or "/" in text:
                results.extend(m.group(0) for m in _WINDOWS_PATH_RE.finditer(text))
                results.extend(m.group(0) for m in _UNIX_PATH_RE.finditer(text))
            # Decode file:// URIs
            for match in _FILE_URI_RE.finditer(text):
                decoded = unquote(match.group(0)[len("file:///") :])
                if decoded:
                    results.append(decoded)
        for child in node.children:
            results.extend(self._find_paths_in_tree(child))
        return results

    @staticmethod
    def _dedupe_paths(paths: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for path in paths:
            normalized = path.strip()
            if not normalized:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result
