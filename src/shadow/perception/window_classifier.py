"""Window Classifier — decide the extraction strategy per window.

Reads process name, window class, and title to identify the window type
(browser, editor, terminal, document, chat, media, notes, other). Each
category determines which perception sources to use and what to extract
(URL, file path, plain text).

This module does not read content. It only decides strategy. The actual
extraction happens in the observer (Commit 9) and the other sources.
"""

import re
from dataclasses import dataclass, field
from enum import StrEnum

from .uia import _TEXT_CONTROL_TYPES  # noqa: F401  (re-export for callers)


class WindowCategory(StrEnum):
    BROWSER = "browser"
    EDITOR = "editor"
    TERMINAL = "terminal"
    DOCUMENT = "document"
    CHAT = "chat"
    MEDIA = "media"
    NOTES = "notes"
    OTHER = "other"


# Process → category. Keys are lowercased, .exe suffix removed.
_DEFAULT_PROCESS_MAP: dict[str, WindowCategory] = {
    # Browsers
    "chrome": WindowCategory.BROWSER,
    "msedge": WindowCategory.BROWSER,
    "firefox": WindowCategory.BROWSER,
    "brave": WindowCategory.BROWSER,
    "opera": WindowCategory.BROWSER,
    "vivaldi": WindowCategory.BROWSER,
    "arc": WindowCategory.BROWSER,
    "zen": WindowCategory.BROWSER,
    # Editors / IDEs
    "code": WindowCategory.EDITOR,
    "code - insiders": WindowCategory.EDITOR,
    "codium": WindowCategory.EDITOR,
    "devenv": WindowCategory.EDITOR,
    "pycharm64": WindowCategory.EDITOR,
    "pycharm": WindowCategory.EDITOR,
    "idea64": WindowCategory.EDITOR,
    "idea": WindowCategory.EDITOR,
    "webstorm64": WindowCategory.EDITOR,
    "goland64": WindowCategory.EDITOR,
    "clion64": WindowCategory.EDITOR,
    "rider64": WindowCategory.EDITOR,
    "sublime_text": WindowCategory.EDITOR,
    "notepad++": WindowCategory.EDITOR,
    "notepad": WindowCategory.EDITOR,
    "atom": WindowCategory.EDITOR,
    "neovim": WindowCategory.EDITOR,
    "vim": WindowCategory.EDITOR,
    "emacs": WindowCategory.EDITOR,
    # Terminals
    "windowsterminal": WindowCategory.TERMINAL,
    "wt": WindowCategory.TERMINAL,
    "cmd": WindowCategory.TERMINAL,
    "powershell": WindowCategory.TERMINAL,
    "pwsh": WindowCategory.TERMINAL,
    "conhost": WindowCategory.TERMINAL,
    "conemu64": WindowCategory.TERMINAL,
    "alacritty": WindowCategory.TERMINAL,
    "wezterm-gui": WindowCategory.TERMINAL,
    "mintty": WindowCategory.TERMINAL,
    "git-bash": WindowCategory.TERMINAL,
    # Documents
    "winword": WindowCategory.DOCUMENT,
    "excel": WindowCategory.DOCUMENT,
    "powerpnt": WindowCategory.DOCUMENT,
    "acrobat": WindowCategory.DOCUMENT,
    "acrord32": WindowCategory.DOCUMENT,
    "sumatrapdf": WindowCategory.DOCUMENT,
    "foxitreader": WindowCategory.DOCUMENT,
    "foxitpdfreader": WindowCategory.DOCUMENT,
    # Chat
    "slack": WindowCategory.CHAT,
    "discord": WindowCategory.CHAT,
    "teams": WindowCategory.CHAT,
    "ms-teams": WindowCategory.CHAT,
    "whatsapp": WindowCategory.CHAT,
    "signal": WindowCategory.CHAT,
    "telegram": WindowCategory.CHAT,
    "zoom": WindowCategory.CHAT,
    # Media
    "spotify": WindowCategory.MEDIA,
    "vlc": WindowCategory.MEDIA,
    "mpv": WindowCategory.MEDIA,
    "music.ui": WindowCategory.MEDIA,
    "photos": WindowCategory.MEDIA,
    "wmplayer": WindowCategory.MEDIA,
    # Notes / second brain
    "obsidian": WindowCategory.NOTES,
    "notion": WindowCategory.NOTES,
    "joplin": WindowCategory.NOTES,
    "logseq": WindowCategory.NOTES,
    "roam": WindowCategory.NOTES,
    "evernote": WindowCategory.NOTES,
    "onenote": WindowCategory.NOTES,
}

# Categories that should never be sampled
_SKIP_CATEGORIES: set[WindowCategory] = set()

# Processes we treat as SHADOW itself (feedback loop guard).
_SELF_PROCESSES = {"python", "pythonw", "shadow", "shadow.exe"}


@dataclass
class WindowProfile:
    """The classifier's verdict on a window."""

    category: WindowCategory
    process: str
    title: str = ""
    class_name: str = ""
    is_self: bool = False
    use_uia: bool = True
    use_ocr: bool = True
    extract_url: bool = False
    extract_path: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "category": self.category.value,
            "process": self.process,
            "title": self.title,
            "class_name": self.class_name,
            "is_self": self.is_self,
            "use_uia": self.use_uia,
            "use_ocr": self.use_ocr,
            "extract_url": self.extract_url,
            "extract_path": self.extract_path,
            "notes": list(self.notes),
        }


# URL detection in a title (browsers put "Title — Site" or similar)
_URL_IN_TITLE = re.compile(r"https?://[^\s]+")

# File path detection (editors put "file.py — folder — App")
_PATH_IN_TITLE = re.compile(r"[\w\-./\\]+\.[A-Za-z]{1,6}\b")


class WindowClassifier:
    """Classifies a window into a category with an extraction strategy."""

    def __init__(self, custom_map: dict[str, str] | None = None):
        self.process_map = dict(_DEFAULT_PROCESS_MAP)
        if custom_map:
            for proc, cat in custom_map.items():
                try:
                    self.process_map[proc.lower().strip()] = WindowCategory(cat)
                except ValueError:
                    continue

    # ---------- public API ----------

    def classify(
        self,
        process: str,
        title: str = "",
        class_name: str = "",
    ) -> WindowProfile:
        """Return a WindowProfile for the given window."""
        normalized = self._normalize_process(process)

        # Self-observation guard
        if self._is_self(normalized, title, class_name):
            return WindowProfile(
                category=WindowCategory.OTHER,
                process=normalized,
                title=title,
                class_name=class_name,
                is_self=True,
                use_uia=False,
                use_ocr=False,
                notes=["self-observation excluded"],
            )

        category = self.process_map.get(normalized, WindowCategory.OTHER)
        profile = WindowProfile(
            category=category,
            process=normalized,
            title=title,
            class_name=class_name,
        )

        self._apply_strategy(profile)
        return profile

    # ---------- internals ----------

    @staticmethod
    def _normalize_process(process: str) -> str:
        if not process:
            return ""
        p = process.strip().lower()
        if p.endswith(".exe"):
            p = p[:-4]
        return p

    @staticmethod
    def _is_self(process: str, title: str, class_name: str) -> bool:
        if process in _SELF_PROCESSES and "shadow" in title.lower():
            return True
        if "silent on-device" in title.lower():
            return True
        return "shadow" in title.lower() and "life context" in title.lower()

    def _apply_strategy(self, profile: WindowProfile) -> None:
        cat = profile.category

        if cat == WindowCategory.BROWSER:
            # Measured (Commit 13 harness): Chromium browsers expose
            # ~90 chars via UIA and ~800 chars via OCR because the UIA
            # tree is gated behind the screen-reader flag. Route to OCR
            # until Microsoft/Chromium changes this, or Phase 3.6
            # Vision supersedes both.
            profile.use_uia = False
            profile.use_ocr = True
            profile.extract_url = True
            profile.notes.append("url extraction enabled; UIA skipped")
            return

        if cat == WindowCategory.EDITOR:
            # Chromium editors (VS Code, Codium, Atom) also expose thin
            # UIA trees. Enable OCR fallback so code content still gets
            # recorded. The change gate bounds OCR cost.
            profile.use_uia = True
            profile.use_ocr = True
            profile.extract_path = True
            profile.notes.append("path extraction enabled; OCR fallback on")
            return

        if cat == WindowCategory.TERMINAL:
            # UIA on modern terminals only surfaces shell chrome, not content.
            profile.use_uia = False
            profile.use_ocr = True
            profile.notes.append("terminal content only via OCR")
            return

        if cat == WindowCategory.DOCUMENT:
            profile.use_uia = True
            profile.use_ocr = True
            return

        if cat == WindowCategory.CHAT:
            profile.use_uia = True
            profile.use_ocr = False
            return

        if cat == WindowCategory.MEDIA:
            # Media apps rarely have useful text; skip extraction entirely.
            profile.use_uia = False
            profile.use_ocr = False
            profile.notes.append("media app; title only")
            return

        if cat == WindowCategory.NOTES:
            profile.use_uia = True
            profile.use_ocr = False
            return

        # OTHER: conservative default
        profile.use_uia = True
        profile.use_ocr = True

    # ---------- title parsing helpers ----------

    @staticmethod
    def extract_url_from_title(title: str) -> str | None:
        """Pull a URL out of a window title, if present."""
        if not title:
            return None
        match = _URL_IN_TITLE.search(title)
        return match.group(0) if match else None

    @staticmethod
    def extract_path_from_title(title: str) -> str | None:
        """Pull a filename (best effort) out of an editor title."""
        if not title:
            return None
        # Editors put the filename first: "recovery.py — shadow — Code"
        head = title.split("—")[0].split(" - ")[0].strip()
        match = _PATH_IN_TITLE.search(head)
        return match.group(0) if match else None
