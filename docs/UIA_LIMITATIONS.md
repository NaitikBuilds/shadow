# UIA Limitations

SHADOW reads the Windows UI Automation tree for structured screen understanding.
Some applications expose their full tree unconditionally; others do not.

## Full UIA tree (always available)

- Notepad, Wordpad
- Microsoft Word, Excel, PowerPoint
- Windows Explorer
- Windows Settings and most system dialogs
- Most legacy Win32 applications
- Most UWP applications

## Partial UIA tree (Chromium-based)

Chrome, Edge, VS Code, Slack, Discord, Obsidian, Notion, Teams, and other
Chromium/Electron apps only expose their full accessibility tree when the
Windows screen-reader flag (`SPI_SETSCREENREADER`) was set **before the app
started**. If the app is already running, it won't see the flag change and
exposes only native title bar controls.

SHADOW sets this flag on startup (`_enable_screen_reader_flag` in
`uia.py`). If Chrome/VS Code was launched *after* SHADOW, its tree is fully
readable. If launched *before*, only the title bar is visible.

## Impact

- **UIA-based extraction**: works on native apps, limited on Chromium apps.
- **OCR fallback**: fills the gap on Chromium apps automatically.
- **Title-based extraction**: works everywhere (URL, file path). This is
  why the Window Classifier flags browsers for URL extraction and editors
  for path extraction — the title always has what we need.

## Not a fix we can make

This is a Windows/Chromium architectural behavior. Every screen reader on
Windows (NVDA, JAWS, Narrator) has the same constraint. Workarounds exist
(launch order, registry flag), but they're fragile and outside SHADOW's
control.

## What we do instead

The observer (Phase 3.5, Commit 9) uses UIA first and falls back to OCR
when the UIA tree is empty or thin. Both paths feed the same memory.

## Browser URLs

Chrome and Edge do not expose their address bar content to UIA unless the
Windows screen-reader flag was set *before* the browser process started.
SHADOW sets this flag on startup, so:

- **If Chrome/Edge was launched after SHADOW:** address bar URLs are readable.
- **If Chrome/Edge was already running:** address bar URLs are not readable.

Page URLs are still available in two cases:
1. The website puts the URL in the window title (rare).
2. OCR fallback picks it up from the top strip of the window (not currently implemented).

**Impact:** URL detection in SHADOW is best-effort for browsers. File path
detection for editors works reliably because editor titles contain the
filename.

**Not a SHADOW bug.** Every Windows screen reader (NVDA, JAWS, Narrator)
has the same constraint. Any future fix must come from a Chromium or
Windows change.

## Reading Position Memory

Reading positions require two signals from the active window:
1. An identifier — URL or file path in the window title.
2. A vertical scroll bar exposed via UIA.

When either is missing, the tracker silently skips the window. This is
by design: partial data is worse than no data.

### Apps that usually work

- VS Code, PyCharm, Sublime Text (path + scroll bar)
- Microsoft Word (path + scroll bar)
- Notepad with a saved long file (path + scroll bar when scrolled)
- Windows Settings with scrollable panels (no identifier, so no persist)

### Apps that don't

- Chrome, Edge, Brave — Chromium doesn't expose scroll bars
- Notepad with untitled content — no file path
- Any app whose title is just "Untitled" or a bare window name

### What we don't do

We don't OCR the scroll bar. That would cost ~200ms per poll and
contradict the "structured not pixels" goal. If a future Windows or
Chromium change exposes scroll bars unconditionally, this feature
automatically improves.

## Routing adjustment (Commit 13.5)

Based on measurements from `scripts/checks/compare_uia_ocr.py`, the
classifier routes:

- **Browsers**: OCR only. UIA produces ~90 chars vs OCR's ~800 chars
  on Chromium browsers. UIA is skipped entirely.
- **Editors**: UIA + OCR fallback. Chromium editors expose thin UIA
  trees; OCR fills in the content.
- **Terminals**: OCR only (unchanged).
- **Everything else**: UIA preferred, OCR fallback.

### When to revert

If any of these change, re-run the harness and adjust:

1. Microsoft/Chromium exposes the full tree without the screen-reader flag.
2. Phase 3.6 Vision provides better browser content than OCR.
3. UIA latency drops significantly on Chromium apps.

Each is a one-file change in `window_classifier.py`.