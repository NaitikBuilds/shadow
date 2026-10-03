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