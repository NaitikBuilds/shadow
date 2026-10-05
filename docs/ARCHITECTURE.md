# SHADOW — Architecture

This document describes how SHADOW is built. For *why* it's built this way, see
[`DECISIONS.md`](DECISIONS.md).

---

## Layered design

SHADOW is organized as a stack of independent layers. Upper layers know nothing
about lower layers' implementation; lower layers are reusable by any upper layer.

```
UI (PySide6)               Chat, consent panel, privacy dashboard
    ↓
Agent Orchestration        Observer worker, insight engines (future)
    ↓
Reasoning / Generation     LLM chat, embeddings (unified backend API)
    ↓
Memory (the Shadow)        SQLite + sqlite-vec, knowledge graph, retention
    ↓
Perception                 Active window, OCR, typing, documents, calendar
    ↓
Hardware Abstraction       CPU backend now; Snapdragon NPU / GPU later
    ↓
Platform Services          Windows APIs, DPAPI, battery, thermal, file system
```

**Rule:** imports only flow downward. `ui/` may import `memory/`, but `memory/`
never imports `ui/`. The `hal/` layer is the only place that knows which
compute backend is in use.

---

## Modules

### `src/shadow/hal/` — Hardware abstraction

- `base.py` — `InferenceBackend` ABC (`generate`, `generate_stream`, `embed`, `info`)
- `cpu_backend.py` — llama.cpp-based chat + embedder wiring
- `onnx_embedder.py` — quantized MiniLM embedder via ONNX Runtime

Only this folder knows about specific hardware. Adding a Snapdragon NPU
backend means adding a new file here and a selection rule in `main.py`.

### `src/shadow/memory/` — Storage layer

- `store.py` — `MemoryStore`, the single SQLite connection. WAL mode,
  thread-safe writes via `RLock`, migration-runner entry point.
- `migrations/` — numbered `.sql` files, `runner.py` applies them in order
- `retriever.py` — semantic + temporal query over observations
- `entities.py` — `EntityExtractor` (rule-based) + `GraphBuilder`
- `retention.py` — prunes old observations, rotates logs
- `recovery.py` — startup consistency pass after a crash

All storage logic lives here. Nothing else opens the database directly.

### `src/shadow/agent/` — Proactive engines

Every engine produces `Insight` objects that the Insight panel renders.

| Engine | Purpose |
|---|---|
| `recovery` | Find abandoned work sessions |
| `forecasting` | Predict near-term needs (30–120 min) |
| `decay` | Flag entities fading from memory |
| `focus` | Detect deep-focus state; filter insights |
| `focus_patterns` | Learn when/where focus is highest |
| `recurring` | Detect weekly activity rhythms |
| `intent_notes` | Extract "note to self" phrases |
| `clipboard_actions` | Classify clipboard content; suggest actions |
| `sessions` | Group observations into coherent work sessions |
| `ambient` | Passive "working on" list |
| `style` | Generate text in the user's voice |
| `dnd` | Global Do Not Disturb toggle |
| `feedback` | Record insight feedback + useful rate |
| `capture` | Global Quick Capture hotkey |

Supporting primitives:

- `insight.py` — `Insight` dataclass
- `prompt_builder.py` — wraps observations in untrusted tags
- `taint.py` — tracks parameter trust levels for future actions

### `src/shadow/perception/` — Observation sources

Each source implements `PerceptionSource`:

```python
class PerceptionSource(ABC):
    name: str          # used as `source` column in observations
    channel: str       # consent channel required to run
    def sample(self) -> dict | None: ...
    def stop(self) -> None: ...  # optional cleanup
```

Sources:

- `active_window.py` — focused window title + process
- `screen_ocr.py` — Windows OCR text of active window
- `screen_uia.py` — UIA text extraction for structured windows
- `typing.py` — keystroke timing (never key content)
- `documents.py` — PDF/TXT/MD/DOCX watcher
- `calendar.py` — `.ics` file reader
- `calendar_winrt.py` — WinRT Appointments (inactive until MSIX)
- `clipboard.py` — clipboard text with secret filtering

Supporting modules (Phase 3.5):

- `uia.py` — UIA element tree reader
- `uia_text.py` — paragraph-level text extraction
- `interactive.py` — buttons, links, inputs extraction
- `window_classifier.py` — category + strategy routing
- `identifiers.py` — URL and file path detection
- `tabs.py` — browser/terminal tab awareness
- `change_detector.py` — perceptual hash for change detection
- `cadence.py` — adaptive poll frequency
- `monitors.py` — multi-monitor awareness
- `reading_position.py` — scroll position + section memory

### Screen routing (Commit 13.5)

The classifier decides which extraction path runs per window:

| Category | UIA | OCR |
|---|---|---|
| Browser | Skip | Primary |
| Editor | Primary | Fallback |
| Terminal | Skip | Primary |
| Document | Primary | Fallback |
| Chat | Primary | Skip |
| Media | Skip | Skip |
| Notes | Primary | Skip |
| Other | Primary | Fallback |

**Reason:** Chromium browsers and Chromium-based editors (VS Code)
expose thin UIA trees. OCR wins on content. See `docs/UIA_LIMITATIONS.md`.

`observer.py` runs the loop that calls `sample()` on each source on a schedule.

### `src/shadow/ui/` — Presentation

- `main_window.py` — chat, mode selector, menu, tray integration
- `consent_panel.py` — per-channel opt-in
- `indicator.py` — "what's being watched" strip
- `privacy_dashboard.py` — consent, activity, wipe
- `notifications.py` — `TrayNotifier` and icon

UI never accesses the DB directly. It calls `MemoryStore` methods.

### `src/shadow/models/` — Model lifecycle

- `registry.py` — declarative list of models (URL, size, role, optional)
- `manager.py` — download, resume, SHA256 verify, version tracking

### `src/shadow/errors.py` — Error classification

`ErrorReporter` with four severities: `Silent` / `Badge` / `Tray` / `Modal`.
Every failure in SHADOW routes through it. Tracebacks go to disk, never to
the database.

### `src/shadow/config.py` — Configuration

Loads `config.yaml`, exposes typed accessors:

- `load_config()`
- `consent_channels()`
- `perception_config()`
- `retention_config()`
- `models_config()`
- `source_enabled()`, `tick_interval()`

Defaults live in code, overrides live in YAML. Merged at load time.

---

## Data flow — the life of one observation

1. **Tick fires.** `ObservationWorker.run()` wakes every
   `tick_interval_sec` (10/30/60 depending on mode).

2. **Idle check.** If the user hasn't touched input for `idle_skip_sec`,
   the tick is skipped entirely.

3. **For each source:**
   - Check `memory.get_consent(source.channel)` — skip if not consented
   - Call `source.sample()` — returns a dict or `None`
   - Extract content string via `_content_from(source_name, payload)`
   - Check dedupe: reject if identical to a recent observation
   - Write to `observations` table
   - Compute embedding via `backend.embed(text)` → write to `vec_observations`
   - Run `GraphBuilder.process()`: extract entities, link them, add edges
   - Emit `observation` signal to UI

4. **UI updates.** The observation indicator shows a brief message.
   The activity log records the event.

5. **Retrieval later.** When the user asks a question, `ShadowRetriever`
   fetches the top-k similar observations (semantic) plus any in the
   requested time window (temporal). These get injected into the LLM
   prompt as untrusted context.

---

## Threading model

Three threads run concurrently:

| Thread | What it does | Lifetime |
|---|---|---|
| **Main (Qt)** | UI rendering, signals, user input | Entire app |
| **Observer (`QThread`)** | Perception loop | Started on launch, stopped on quit |
| **Inference (`QThread`)** | One LLM generation at a time | Spawned per query |

### Synchronization

- **SQLite** — one shared connection, WAL mode, all writes wrapped in
  `MemoryStore._lock` (`RLock`). Reads are lock-free.
- **Qt signals** — the only way threads talk to the UI. No shared state
  besides `MemoryStore`.
- **Kill switch** — `worker.requestInterruption()` sets a flag checked
  between tokens. Observer checks `isInterruptionRequested()` in its sleep
  loop.

### Shutdown

Closing the window minimizes to tray (via `setQuitOnLastWindowClosed(False)`).
Full quit is via tray menu or `Ctrl+C`. `closeEvent` calls
`observer.stop()` → `worker.requestInterruption()` → `memory.close()`.

---

## Database schema

Nine tables + two virtual tables. All migrations live in
`src/shadow/memory/migrations/`.

| Table | Purpose |
|---|---|
| `observations` | Every observed event (text content + metadata) |
| `vec_observations` | 384-dim embeddings (sqlite-vec virtual table) |
| `entities` | Knowledge graph nodes (project/topic/file) |
| `edges` | Weighted relations between entities |
| `observation_entities` | Many-to-many link table |
| `consents` | Per-channel opt-in state |
| `consent_audit` | Audit log of consent toggles |
| `activity_log` | All user-visible events |
| `intentions` | (Reserved for Phase 3) |
| `schema_meta` | Migration version + model hashes + prune timestamp |
| `insight_feedback` | 👍/👎 verdicts on insights |
| `ambient_task_state` | Dismiss/promote decisions for ambient list |
| `tab_state` | Open tab tracking (first_seen, last_active) |
| `reading_positions` | Scroll position + section per document |

**WAL mode** is enabled on every connection. `foreign_keys=ON` also set
per-connection.

---

## Configuration

`config.yaml` at the repo root. Sections:

- `model:` — paths, context size, thread count, embedder paths
- `memory:` — DB path, vector dimension
- `models:` — model cache directory, verify policy
- `consent:` — initial consent state (user overrides via UI)
- `observation:` — indicator position, mode default
- `perception:` — tick intervals, per-source toggles, entity extraction config
- `modes:` — Lite / Balanced / Active overrides
- `retention:` — prune windows and intervals

Defaults are in `config.py`. The YAML only needs to specify overrides —
partial blocks are merged with defaults at load time.

---

## Extension points

**Adding a new perception source:**

1. Subclass `PerceptionSource` in `src/shadow/perception/`
2. Define `name` and `channel`
3. Implement `sample()` → returns dict or `None`
4. Register it in `ObservationWorker.__init__`
5. Add a content-formatting branch in `observer._content_from()`
6. Add tests in `tests/test_<name>.py`

**Adding a new LLM backend:**

1. Subclass `InferenceBackend` in `src/shadow/hal/`
2. Implement `generate`, `generate_stream`, `embed`, `info`
3. Register it in `main.py` based on hardware detection

**Adding a new table:**

1. Create `src/shadow/memory/migrations/00N_description.sql`
2. Include `CREATE TABLE IF NOT EXISTS` and any indexes
3. Restart SHADOW — the runner applies it automatically
4. Add helpers to `MemoryStore` if needed

**Adding a new UI surface:**

1. Create a `QWidget` subclass in `src/shadow/ui/`
2. Wire it into `MainWindow` via a menu action or panel
3. Never import `sqlite3` directly — go through `MemoryStore`

---

## Testing strategy

- **Unit tests** — pure logic (entities, migrations, config)
- **Integration tests** — `MemoryStore` with a temp DB
- **Perception tests** — `sample()` returns valid payload or `None`
- **UI tests** — constructs without crashing; Qt signals fire

Pytest markers:

- `@pytest.mark.slow` — loads models; skipped in dev, run in CI manually
- `@pytest.mark.hardware("snapdragon")` — hardware-specific
- `@pytest.mark.injection` — security scenarios (Phase 4.5b)

**Network isolation** is enforced by `scripts/check_network_isolation.py` in
CI: no imports of `requests`, `socket`, `urllib`, etc. in `src/shadow/`
outside the model-manager whitelist.

---

## Performance targets

| Operation | Target |
|---|---|
| Observer tick | < 100 ms (excluding OCR) |
| OCR pass | 200–500 ms |
| Embedding | 100–300 ms |
| Chat first-token latency | 2–4 s |
| Chat full response (256 tokens) | 8–15 s |
| Startup to ready | 15 s (CPU) |
| Wipe | < 5 s |

Numbers from Phase 2 benchmarks on an i5-12450H, 16 GB RAM.

---

## Directory layout

```
shadow/
├── src/shadow/
│   ├── agent/            (Phase 3+)
│   ├── hal/              # Hardware abstraction
│   ├── memory/           # Storage, retrieval, graph
│   │   └── migrations/   # Numbered SQL files
│   ├── models/           # Model download + cache
│   ├── perception/       # Observation sources
│   ├── ui/               # PySide6 widgets
│   ├── config.py
│   ├── errors.py
│   └── main.py           # Entry point
├── tests/                # Pytest suite
├── scripts/              # Dev tooling
│   ├── checks/           # Inspection scripts
│   └── data/             # Model + fixture tooling
├── docs/                 # Architecture, decisions, guides
├── data/                 # SQLite DB + backups (gitignored)
├── models/               # Downloaded models (gitignored)
├── logs/                 # Error logs (gitignored)
├── benchmarks/           # Benchmark results (gitignored)
└── config.yaml
```

---

## Key invariants

- **No network calls from the main process.** Enforced by CI.
- **Every observation is consent-gated.** Enforced by `observer._do_tick`.
- **Every write is transaction-safe.** WAL mode + `_lock`.
- **Every schema change goes through a migration.** No exceptions.
- **Every error is classified.** No untyped exceptions reach the UI.
- **Imports flow downward only.** No circular dependencies between layers.
- **Tracebacks never touch the DB.** They go to `logs/errors_*.log`.
- **Every insight flows through one dataclass.** Engines don't touch UI.
- **Every LLM call with observations uses PromptBuilder.**
- **Every observation is redacted before storage and embedding.**
- **All timestamps are UTC.** No local-time comparisons anywhere.

---

*Last updated: Phase 2.5 complete.*