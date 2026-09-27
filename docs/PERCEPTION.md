# Perception Layer

The perception layer watches the user's context and writes observations to memory. Every source is:

- **Consent-gated** — nothing runs without explicit user opt-in
- **Local-only** — no network calls
- **Duty-cycled** — respects Lite / Balanced / Active modes
- **Dedupe-aware** — identical content within a time window isn't re-recorded

---

## Sources

### `active_window` (channel: `screen_capture`)

Reads the title and process name of the currently focused window via `pywin32`.

Writes one observation per tick when the window changes. Skips empty or system windows.

**Payload fields:** `title`, `process`, `pid`, `timestamp`

---

### `screen_ocr` (channel: `screen_capture`)

Captures the pixels of the active window, runs Windows OCR (WinRT), and extracts visible text.

Runs on every Nth tick (configurable, default 3) to keep CPU load down. Filters out low-quality OCR results — terminal garbage, symbol-heavy text, and case chaos are dropped.

**Payload fields:** `text`, `word_count`, `timestamp`

---

### `typing_dynamics` (channel: `typing_dynamics`)

Tracks keystroke **timing only** (never key values) via `pynput`. Computes:

- Keystrokes per minute
- Mean inter-key interval
- Pause count (gaps > 2 s)
- Longest pause
- Focus score (0–1 heuristic)

Writes one observation per tick when at least `min_keystrokes` (default 10) were recorded.

**Payload fields:** `keystrokes`, `duration_sec`, `kpm`, `mean_interval_ms`, `pause_count`, `longest_pause_sec`, `focus_score`, `summary`, `timestamp`

**Privacy note:** The keyboard callback receives the key object from pynput and discards it immediately. Only the monotonic timestamp is retained. No key values are ever stored.

---

### `document` (channel: `document_parsing`)

Watches configured folders (`~/Documents`, `~/Downloads` by default) for `.pdf`, `.txt`, `.md`, `.docx` files modified since SHADOW started.

Extracts text and writes one observation per tick (the most recently modified file). Files modified before SHADOW started are ignored — the source seeds its "seen" map on first tick.

**Payload fields:** `path`, `name`, `extension`, `char_count`, `text`, `timestamp`

---

### `calendar` (channel: `calendar`)

Reads `.ics` files from configured folders. Emits one event per tick from the time window `[now - lookback_days, now + lookahead_days]` (defaults: 1 day back, 14 days forward). Each event is tagged `past`, `ongoing`, or `upcoming`.

**Payload fields:** `uid`, `summary`, `start`, `end`, `location`, `description`, `status`, `content`, `source_backend` (`"ics"`), `timestamp`

---

### `calendar_winrt` (channel: `calendar`)

Reads the Windows consolidated calendar store via the WinRT Appointments API. **Requires MSIX packaging** for the `appointments` capability.

In unpackaged builds, this source logs one diagnostic message and returns `None` on every tick — it's present but inactive. Once SHADOW ships as a packaged app, it activates automatically.

**Payload fields:** `uid`, `summary`, `start`, `end`, `location`, `description`, `status`, `content`, `source_backend` (`"winrt"`), `timestamp`

See [`CALENDAR.md`](CALENDAR.md) for the full permission model.

---

## Duty cycling

The observer runs on a schedule defined by the current mode:

| Mode | Tick interval |
|---|---|
| Lite | 60 s |
| Balanced | 30 s |
| Active | 10 s |

Switching modes at runtime takes effect on the next tick.

**Idle detection:** if the user hasn't touched keyboard or mouse for `idle_skip_sec` (default 120 s), ticks are skipped entirely. The observer resumes immediately when input is detected.

**Dedupe:** identical content within `dedupe_window_sec` (default 60 s) is not re-recorded. A fuzzy dedupe on the first 80 characters catches near-duplicates across a longer window.

---

## Consent

Every source maps to a consent channel. Users toggle channels in **Settings → Consent…**. The observer checks `memory.get_consent(channel)` before running each source.

There are two gates:

1. **Config gate** (`perception.sources.<name>`) — is the source available in this build?
2. **Consent gate** (`consents` table) — has the user opted in?

Both must be true for a source to sample. This allows shipping with all sources available while defaulting to privacy — nothing runs until the user enables it.

### Consent channels

| Channel | Sources using it |
|---|---|
| `screen_capture` | `active_window`, `screen_ocr` |
| `typing_dynamics` | `typing_dynamics` |
| `document_parsing` | `document` |
| `calendar` | `calendar`, `calendar_winrt` |
| `meeting_audio` | (reserved, not yet implemented) |
| `webcam_posture` | (reserved, not yet implemented) |

Multiple sources can share one channel. The user sees one toggle, and both sources are gated by it.

---

## Observer loop

The `ObservationWorker` is a `QThread` that:

1. Wakes every `tick_interval_sec`
2. Checks idle state — skips the tick if user is idle
3. Iterates registered sources
4. For each source: checks consent, calls `sample()`, extracts content, dedupes, writes to memory, builds graph
5. Emits Qt signals for UI updates: `tick`, `observation`, `skipped`, `error`

Writes are serialized with an `RLock` on `MemoryStore` so the observer thread and UI thread can safely share the SQLite connection.

---

## Knowledge graph

Every observation is passed through `GraphBuilder`, which:

1. Extracts entities (projects, topics, files) via rule-based `EntityExtractor`
2. Upserts each entity into the `entities` table
3. Links the observation to its entities via `observation_entities`
4. Adds bidirectional co-occurrence edges between entities in the same observation

This builds a graph of what co-occurs with what — enabling Phase 3 agentic features like Cross-Project Insight Weaver.

### Entity types

| Type | Rule | Example |
|---|---|---|
| `project` | Matches a name in `known_projects` config (case-insensitive substring) | `SHADOW`, `Phase 2` |
| `topic` | Capitalized phrase, 1–3 words, stopword-filtered | `Visual Studio Code`, `ONNX Runtime` |
| `file` | Filename with a known extension | `observer.py`, `config.yaml` |

Stopwords (articles, months, OS chrome) are stripped token-by-token. `"The Observer pattern"` becomes topic `"Observer"`.

### Edge accumulation

Co-occurrence edges have weight `0.1` per occurrence and accumulate. If SHADOW sees `SHADOW` and `observer.py` together 20 times, the edge weight becomes `2.0`. This gives Phase 3 a natural ranking signal.

---

## Extending the layer

To add a new source:

1. Subclass `PerceptionSource` in `src/shadow/perception/`
2. Define `name` (used as `source` in the observations table) and `channel` (consent key)
3. Implement `sample()` → returns dict or None
4. Optionally implement `stop()` for cleanup
5. Register in `ObservationWorker.__init__`, gated by `source_enabled(config, "<name>")`
6. Add the `source_name` branch to `_content_from` if the payload needs a specific string format
7. Add tests in `tests/test_<name>.py`
8. Document it in this file