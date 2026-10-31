"""Detect SHADOW's own windows so the perception layer never observes them.

Every SHADOW window has a recognisable title pattern. Combined with a
process check (shadow.exe when packaged, python.exe in dev), this module
identifies self-windows without false-positives on other apps.

Why the process+title pair, not just "python.exe":
  - A user running another Python script (a notebook, a script) must NOT
    be excluded just because the process name matches.
  - SHADOW's own dialogs are recognisable by title prefix, so requiring
    BOTH conditions keeps unrelated Python apps observable.
"""

from __future__ import annotations

import os

# Titles SHADOW itself produces. Match is "equals" OR "startswith".
SHADOW_TITLE_PREFIXES: tuple[str, ...] = (
    "SHADOW",
    "SHADOW —",
    "SHADOW -",
    "Clone:",
    "Ethical Mirror",
    "Reflection",
    "Send this reflection to cloud?",
    "SHADOW — Vision",
    "SHADOW — Search",
    "SHADOW — Privacy",
    "SHADOW — Diagnostics",
    "SHADOW — Consent",
    "SHADOW — Cloud",
    "SHADOW — Settings",
    "SHADOW — Ambient",
    "SHADOW — Insights",
)

# Process basenames (lowercase) that could be SHADOW.
SELF_PROCESS_NAMES = frozenset(
    {
        "shadow.exe",
        "shadow",
        "shadow-dev.exe",
        "python.exe",
        "python3.exe",
        "pythonw.exe",
        "python3w.exe",
    }
)


def _basename_lc(process: str | None) -> str:
    if not process:
        return ""
    return os.path.basename(str(process)).lower()


def is_shadow_process(process: str | None) -> bool:
    """True if the process name *could* be SHADOW. Never used alone —
    always combined with a title check."""
    return _basename_lc(process) in SELF_PROCESS_NAMES


def is_shadow_title(title: str | None) -> bool:
    """True if the title matches one of SHADOW's own window-title patterns."""
    t = (title or "").strip()
    if not t:
        return False
    for prefix in SHADOW_TITLE_PREFIXES:
        if (
            t == prefix
            or t.startswith(prefix + " ")
            or t.startswith(prefix + "—")
            or t.startswith(prefix + "-")
            or t.startswith(prefix + ":")
        ):
            return True
    return False


def is_shadow_window(sample: dict) -> bool:
    """True if this active-window sample describes a SHADOW window.

    Accepts common field names from different sample() implementations.
    """
    proc = (
        sample.get("process") or sample.get("process_name") or sample.get("exe") or ""
    )
    title = sample.get("title") or sample.get("window_title") or ""
    return is_shadow_process(proc) and is_shadow_title(title)


def is_shadow_text(text: str | None) -> bool:
    """Defence in depth: True if `text` looks like it begins with a
    SHADOW title pattern (used by filters that only see extracted text)."""
    if not text:
        return False
    t = text.strip()
    return any(t.startswith(p) for p in SHADOW_TITLE_PREFIXES)
