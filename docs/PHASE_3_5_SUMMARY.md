# Phase 3.5 — Structured Screen Understanding

**Status:** Complete | **Commits:** 14 | **Duration:** ~2 weeks part-time

## What was built

### Structured screen reading (UIA)
- Element tree reader with depth and element caps
- Password-field exclusion (with children)
- Offscreen element filtering
- Icon-glyph noise filter
- COM initialization per thread

### Routing and extraction
- `WindowClassifier` — 8 categories, 70+ process mappings
- `UIATextExtractor` — paragraph-level text, heading detection
- `InteractiveExtractor` — buttons, links, inputs by role
- `IdentifierExtractor` — URLs and file paths with dedup + normalization
- `ScreenUIASource` — integrated with observer

### Signal quality
- `ChangeDetector` — dhash perceptual hash, Hamming distance
- `AdaptiveCadence` — dynamic poll interval from change signal
- `MonitorInfo` — multi-monitor bounds, DPI, work area
- `TabReader` + `TabStateTracker` — tab list, staleness, related groups
- `ReadingPositionReader` + `ReadingPositionTracker` — scroll + section

### Agent-side additions
- `StuckDetector` — static window, alternation, error patterns
- UIA vs OCR comparison harness (`scripts/checks/compare_uia_ocr.py`)

## Measured results

| Category | UIA chars | OCR chars | Winner |
|---|---|---|---|
| Browser | ~45 | ~700 | OCR |
| Editor | ~100 | ~800 | OCR |
| Terminal | 0 (skipped) | ~600 | OCR |
| Other | ~290 | ~280 | UIA (tie) |

Routing adjusted in Commit 13.5 to reflect this: browsers OCR-only,
editors with OCR fallback.

## Known limitations

- Chromium apps (Chrome, Edge, VS Code, Slack, Obsidian) don't expose
  their content layer to UIA without the screen-reader flag set at process
  startup. See `UIA_LIMITATIONS.md`.
- Reading position memory works for native apps and sometimes for editors;
  browsers blocked.

## What Phase 3.6 will add

- VLM-based visual understanding fills the content gap on Chromium apps.
- Region capture (Circle-to-Ask).
- Screen context queries ("what am I looking at?").