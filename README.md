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
| Infrastructure hardening | 🚧 In progress |
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

## Tests

```powershell
pytest
```

The suite covers local memory, consent handling, perception sources, entity extraction, and the observer loop.

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

If you'd like to know more about the direction of the project for collaboration, research, or press purposes, contact me via GitHub.

---

## Contact

- GitHub: [@NaitikBuilds](https://github.com/NaitikBuilds)
- Issues: welcome for bugs and security concerns
- Pull requests: not accepted at this time

---

*SHADOW is a personal research project. It is not affiliated with any company, and it is not a product.*