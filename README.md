# SHADOW

A local-first research project exploring context-aware desktop assistance.

> ⚠️ **Early development.** This is a personal work-in-progress. Not ready for general use, not a released product, and not accepting external contributions at this time.

---

## About

SHADOW is a personal research project investigating how a desktop application can observe and understand its own environment locally — without sending data to any cloud service.

The project is developed in the open for learning and portfolio purposes, but is not a public product. There is no installer, no release, and no support.

**What this repo contains today:** an early-stage experimental implementation of local observation and retrieval on Windows. It runs entirely offline.

**What this repo is not:** a finished tool, a product announcement, or a description of the full research direction. The design documentation is maintained separately and is not included here.

---

## Status

| Phase | State |
|---|---|
| Foundation | ✅ Complete |
| Core local observation + retrieval | ✅ Complete |
| Extended perception | ✅ Complete |
| Infrastructure hardening | ✅ Complete |
| Further features | 🔒 Private roadmap |

Development is part-time and ongoing. No release schedule.

---

## What works right now

- Runs fully offline on Windows (no network calls)
- Local observation of basic desktop context (opt-in, per-channel consent)
- Local vector memory with semantic and temporal retrieval
- Local knowledge graph built from observations
- Consent controls, activity log, and one-click local data wipe
- Streaming chat interface backed by a small local language model
- Versioned database migrations with automatic backups
- System tray integration with minimize-to-tray
- Retention policies and crash recovery
- Structured error taxonomy with categorized notifications

Everything runs on-device. Nothing leaves the machine.

---

## Requirements

- **Windows 10 or 11**
- **Python 3.11** (3.12+ not supported yet)
- **16 GB RAM minimum** (24 GB recommended for future work)
- **~15 GB free disk** for local models
- Modern multi-core CPU (Intel 11th Gen / AMD Ryzen 5000 or newer)

---

## Setup

```powershell
# 1. Clone
git clone https://github.com/NaitikBuilds/shadow.git
cd shadow

# 2. Create a Python 3.11 virtual environment
py -3.11 -m venv .venv
.venv\Scripts\activate

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Download local models (~1.2 GB)
python scripts/download_model.py
python scripts/download_embedder.py

# 5. Run
shadow
```

On first launch, all observation channels are **off**. Enable only what you want in `Settings → Consent`.

---

## Privacy

- **Local-only.** No network calls from the core application.
- **Opt-in.** Every sensing channel requires explicit consent.
- **Transparent.** All observations are logged and viewable.
- **Erasable.** One-click full wipe of local data.
- **No telemetry.** No analytics, no crash reporting, no usage tracking.
- **No training on your data.** Ever.

---

## Tech stack

- Python 3.11
- PySide6 (UI)
- llama.cpp via `llama-cpp-python` (local LLM runtime)
- ONNX Runtime + quantized MiniLM (local embeddings)
- SQLite + `sqlite-vec` (local vector storage)
- Windows OCR engine (for text extraction from screen)
- `pywin32`, `psutil` (Windows integration)
- `pypdf`, `python-docx`, `icalendar` (document and calendar parsing)

Everything is open-source and runs locally.

---

## Project structure

```
shadow/
├── src/shadow/
│   ├── hal/              # Hardware abstraction (CPU today)
│   ├── memory/           # SQLite + vectors + knowledge graph
│   │   └── migrations/   # Versioned schema migrations
│   ├── models/           # Model download and cache
│   ├── perception/       # Observation sources
│   ├── ui/               # PySide6 widgets
│   ├── config.py
│   ├── errors.py
│   └── main.py
├── tests/                # Pytest suite
├── scripts/              # Dev tooling
│   ├── checks/           # Inspection scripts
│   └── data/             # Model and fixture tooling
├── docs/                 # Architecture, decisions, guides
└── config.yaml
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full architecture
and [`docs/DECISIONS.md`](docs/DECISIONS.md) for why things are the way they
are.

---

## Tests

```powershell
pytest
```

The suite covers local memory, consent handling, perception sources, entity
extraction, migrations, model management, error routing, retention, and crash
recovery.

Pytest markers:

- `slow` — loads models (skipped in dev, run manually when needed)
- `hardware("name")` — requires specific hardware
- `injection` — security scenarios
- `network` — network isolation checks

Run fast tests only:

```powershell
pytest -m "not slow and not hardware and not injection"
```

---

## Useful dev scripts

```powershell
# Inspection
python scripts/checks/check_schema.py        # DB schema version and row counts
python scripts/checks/check_wal.py           # verify WAL mode is active
python scripts/checks/check_retention.py     # last prune time and counts
python scripts/checks/check_graph.py         # knowledge graph snapshot
python scripts/checks/check_documents.py     # document observation status
python scripts/checks/check_calendar.py      # calendar observation status
python scripts/checks/check_typing.py        # typing dynamics observations
python scripts/checks/find_debug_prints.py   # scan for leftover debug code

# Tooling
python scripts/manage_models.py list         # model status
python scripts/data/seed_demo_observations.py  # populate test data
python scripts/data/make_test_calendar.py    # generate a test .ics file
python scripts/check_install.py              # verify editable install
python scripts/check_network_isolation.py    # verify no network calls in core
python scripts/run_benchmarks.py             # latency benchmarks
```

---

## Why this is public

Two reasons:

1. **Learning.** Building in the open keeps the project honest and well-documented.
2. **Portfolio.** It demonstrates an approach to building fully local, privacy-first desktop software.

It is **not** an invitation to copy, fork for commercial use, or build a competing product. The license below makes that explicit.

---

## License

**Business Source License 1.1 (BSL 1.1)** — see [`LICENSE`](LICENSE) and [`NOTICE.md`](NOTICE.md).

- ✅ Free for personal, educational, and research use
- ✅ Read, learn from, and study the code
- ❌ Commercial use requires a separate license
- 🔄 Automatically converts to Apache 2.0 four years after first public release

If you'd like to discuss licensing, open an issue.

---

## Design documentation

The full design specification is **not included in this repository**. It is maintained privately during development.

Public design docs that *are* included:

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — how SHADOW is built
- [`docs/DECISIONS.md`](docs/DECISIONS.md) — why it's built that way
- [`docs/PERCEPTION.md`](docs/PERCEPTION.md) — perception sources reference
- [`docs/CALENDAR.md`](docs/CALENDAR.md) — calendar integration notes
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — public roadmap summary

---

## Contact

- GitHub: [@NaitikBuilds](https://github.com/NaitikBuilds)
- Issues: welcome for bugs and security concerns
- Pull requests: not accepted at this time

---

*SHADOW is a personal research project. It is not affiliated with any company, and it is not a product.*