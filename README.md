# SHADOW

**Silent On-Device Life Context Agent**

A fully local, background-running multimodal AI agent that builds a private digital representation of the user's knowledge, intentions, emotional patterns, and unfinished work — called the **Shadow**.

SHADOW runs entirely on your own device. No cloud. No telemetry. No training on your data.

---

## Status

🚧 **Phase 2 complete** — Perception layer

| Phase | Status |
|---|---|
| Phase 0 — Foundation | ✅ Complete |
| Phase 1 — Core Shadow | ✅ Complete |
| Phase 2 — Perception | ✅ Complete |
| Phase 3 — Agent features | Next |
| Phase 4 — Advanced features | Planned |
| Phase 5 — Snapdragon NPU | Planned |
| Phase 6 — MSIX packaging | Deferred |

Current release: **v0.2.0-perception**

---

## Design Philosophy

> Runs well everywhere, dramatically better on Snapdragon.

- **CPU path (default):** Fully functional on any modern Windows laptop.
- **Snapdragon path (enhanced):** Automatic acceleration on Hexagon NPU when available.
- **Optional GPU path:** Offload selected workloads when a capable GPU is present.

---

## Architecture

```
Presentation        PySide6 UI, tray, dashboard
        ↓
Agent Orchestration Triggers, scheduler, modes
        ↓
Reasoning/Generation Local LLM (Qwen2.5-1.5B Q4)
        ↓
Understanding       OCR (Windows), embeddings (ONNX MiniLM)
        ↓
Memory              SQLite + sqlite-vec + knowledge graph
        ↓
Perception          Active window, OCR, typing, documents, calendar
        ↓
HAL                 CPU backend (Snapdragon NPU planned)
        ↓
Platform Services   DPAPI, battery, process priority
```

---

## Features

### Core (Phase 1)

- **Consent-driven observation** — every sensing channel requires explicit opt-in
- **Local vector memory** — SQLite + sqlite-vec, no cloud
- **Semantic retrieval** — MiniLM embeddings power "what was I working on?"
- **Temporal query** — ask about your own past ("what did I think about last month?")
- **Knowledge graph** — entities and co-occurrence edges built from observations
- **Privacy Dashboard** — consent state, activity log, one-click wipe
- **Streaming LLM responses** — text appears word by word
- **Lite / Balanced / Active modes** — adjust observation frequency on the fly
- **Graceful shutdown** — no background thread leaks, DB closes cleanly

### Perception (Phase 2)

Six sources, each gated by its own consent channel:

| Source | Consent channel | What it captures |
|---|---|---|
| `active_window` | `screen_capture` | Window title + process name |
| `screen_ocr` | `screen_capture` | Visible text of the active window |
| `typing_dynamics` | `typing_dynamics` | Keystroke rhythm, pause patterns, focus score |
| `document` | `document_parsing` | PDF / TXT / MD / DOCX content |
| `calendar` | `calendar` | Events from `.ics` files |
| `calendar_winrt` | `calendar` | Native Windows calendar (requires MSIX packaging) |

See [`docs/PERCEPTION.md`](docs/PERCEPTION.md) and [`docs/CALENDAR.md`](docs/CALENDAR.md) for details.

---

## Tech Stack

- **Language:** Python 3.11
- **UI:** PySide6
- **LLM runtime:** llama-cpp-python (CPU wheels)
- **LLM model:** Qwen2.5-1.5B-Instruct Q4_K_M
- **Embeddings:** ONNX Runtime + all-MiniLM-L6-v2 (quantized)
- **Memory:** SQLite + sqlite-vec
- **OCR:** Windows OCR engine (WinRT)
- **Typing:** pynput (timing only — no key values recorded)
- **Windows integration:** pywin32, psutil
- **Documents:** pypdf, python-docx
- **Calendar:** icalendar, WinRT Appointments API

---

## Quick Start

### Prerequisites

- **Python 3.11** (not 3.12+, not 3.14 — wheels aren't ready)
- **Windows 10 or 11**
- **16 GB RAM** recommended (8 GB possible with small models)
- **10–15 GB free disk** for models
- **Intel 11th Gen / AMD Ryzen 5000** or newer recommended

### Setup

```powershell
# 1. Clone the repo
git clone https://github.com/NaitikBuilds/shadow.git
cd shadow

# 2. Create virtual environment with Python 3.11
py -3.11 -m venv .venv
.venv\Scripts\activate

# 3. Install SHADOW and dependencies
pip install -e ".[dev]"

# 4. Download the LLM (~1.1 GB)
python scripts/download_model.py

# 5. Download the embedder (~90 MB)
python scripts/download_embedder.py

# 6. Run SHADOW
shadow
```

### First run

1. SHADOW opens with a chat window. All perception sources are **off**.
2. Open **Settings → Consent…** and enable the channels you want.
3. The observation indicator updates to show what's currently being watched.
4. Ask something like `What was I working on recently?` once observations accumulate.
5. Open **Settings → Privacy Dashboard…** to inspect and wipe local memory at any time.

---

## Privacy

SHADOW is built privacy-first:

- **Local-only:** No core intelligence requires network access.
- **Opt-in:** Nothing is observed without explicit consent per channel.
- **Transparent:** Every observation is logged and viewable in the Privacy Dashboard.
- **Erasable:** One-click full wipe in under 5 seconds.
- **Encrypted at rest:** Windows DPAPI (planned).
- **No training:** Your data is never used to train shared models.

**What is NOT recorded:**

- Typing: only timing (interval, pauses, focus score) — never key values.
- Screen: only text extracted via OCR — no images stored.
- Webcam: not implemented yet.

---

## Development

### Running tests

```powershell
pytest
```

80+ tests covering memory, perception, entity extraction, calendar ingestion, and the observer loop.

### Useful dev scripts

```powershell
python scripts/check_install.py              # verify editable install is active
python scripts/check_graph.py                # inspect knowledge graph
python scripts/check_documents.py            # inspect document observations
python scripts/check_calendar.py             # inspect calendar observations
python scripts/check_typing.py               # inspect typing observations
python scripts/seed_demo_observations.py     # seed fake observations for testing
python scripts/make_test_calendar.py         # generate a test .ics file
```

### Project structure

```
shadow/
├── src/shadow/
│   ├── hal/              # Hardware abstraction layer
│   │   ├── base.py       # InferenceBackend interface
│   │   ├── cpu_backend.py
│   │   └── onnx_embedder.py
│   ├── memory/           # Local storage
│   │   ├── store.py      # SQLite + sqlite-vec
│   │   ├── entities.py   # Entity extraction + graph builder
│   │   └── retriever.py  # Semantic + temporal retrieval
│   ├── perception/       # Observation sources
│   │   ├── base.py       # PerceptionSource interface
│   │   ├── active_window.py
│   │   ├── screen_ocr.py
│   │   ├── typing.py
│   │   ├── documents.py
│   │   ├── calendar.py
│   │   ├── calendar_winrt.py
│   │   └── observer.py   # Duty-cycled background loop
│   ├── ui/               # PySide6 UI
│   │   ├── main_window.py
│   │   ├── consent_panel.py
│   │   ├── indicator.py
│   │   └── privacy_dashboard.py
│   ├── config.py         # YAML config loader
│   └── main.py           # Entry point
├── tests/                # pytest suite
├── scripts/              # Dev helpers
├── docs/                 # Roadmap, perception, calendar docs
├── config.yaml           # Runtime configuration
└── pyproject.toml
```

---

## Configuration

`config.yaml` controls models, memory paths, observation modes, and per-source settings. Key blocks:

```yaml
model:
  path: "models/qwen2.5-1.5b-instruct-q4_k_m.gguf"
  embedder_model: "models/minilm/model.onnx"
  embedder_tokenizer: "models/minilm/tokenizer.json"

memory:
  db_path: "data/shadow.db"
  vector_dim: 384

consent:                 # initial consent state (user toggles in UI)
  screen_capture: false
  document_parsing: false
  meeting_audio: false
  calendar: false
  typing_dynamics: false
  webcam_posture: false

modes:
  default: "balanced"
  lite:     { observation_interval_sec: 60, model_max_tokens: 128 }
  balanced: { observation_interval_sec: 30, model_max_tokens: 256 }
  active:   { observation_interval_sec: 10, model_max_tokens: 512 }

perception:
  enabled: true
  tick_interval_sec: 30
  idle_skip_sec: 120
  ocr_every_n_ticks: 3
  dedupe_window_sec: 60
  sources:
    active_window: true
    screen_ocr: true
    typing_dynamics: true
    document_watch: true
    calendar: true
  documents:
    watch_folders: ["~/Documents", "~/Downloads"]
    extensions: [".pdf", ".txt", ".md", ".docx"]
    max_file_size_mb: 5
    max_chars: 4000
  calendar:
    watch_folders: ["~/Documents", "~/Downloads"]
    lookback_days: 1
    lookahead_days: 14
  entity_extraction:
    enabled: true
    known_projects: ["SHADOW", "Phase 1", "Phase 2", "Phase 3"]
```

---

## Roadmap

- **Phase 3 (next):** Unfinished-work recovery, Intention Forecasting, Style Mirror, Knowledge Decay Detection, Contextual Focus Shield, Adaptive Observation Budget
- **Phase 4:** Shadow Cloning, Ethical Mirror, Cross-Project Insight Weaver, Silent Pair Partner
- **Phase 5:** Snapdragon Hexagon NPU routing (QNN), Battery-Aware and Thermal-Aware scaling
- **Phase 6:** MSIX packaging + `appointments` capability (activates WinRT calendar)
- **Future:** Webcam posture, multi-device Shadow continuity, domain packs, Intel NPU / AMD / Apple Silicon backends

Full details in [`docs/ROADMAP.md`](docs/ROADMAP.md).

---

## Requirements

### Minimum (CPU path)

- Windows 10/11
- Intel 11th Gen / AMD Ryzen 5000 or newer
- 16 GB RAM
- 10–15 GB free storage for models + Shadow growth

### Recommended

- Intel 12th Gen or newer / AMD Ryzen 6000+
- 16–32 GB RAM
- 20+ GB free storage
- Good cooling for sustained observation

### Enhanced (Snapdragon path, future)

- Snapdragon X or X2 series
- Windows on Snapdragon
- 16+ GB RAM

---

## License

MIT — see [`LICENSE`](LICENSE).

---

## Acknowledgments

Built on the shoulders of:

- [llama.cpp](https://github.com/ggerganov/llama.cpp) for efficient CPU inference
- [sqlite-vec](https://github.com/asg017/sqlite-vec) for local vector search
- [sentence-transformers](https://www.sbert.net/) for the MiniLM embedder
- [PySide6](https://doc.qt.io/qtforpython/) for the UI framework

---

**SHADOW is designed to run on your hardware, respect your privacy, and never phone home.**