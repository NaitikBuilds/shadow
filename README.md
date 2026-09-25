# SHADOW

**Silent On-Device Life Context Agent**

A fully local, background-running multimodal AI agent that builds a private digital representation of the user's knowledge, intentions, emotional patterns, and unfinished work — called the **Shadow**.

SHADOW is designed to run entirely on your own device. No cloud. No telemetry. No training on your data.

## Status

🚧 Early development — Phase 0 (Foundation)

## Design Philosophy

> Runs well everywhere, dramatically better on Snapdragon.

- **CPU path (default):** Fully functional on any modern Windows laptop.
- **Snapdragon path (enhanced):** Automatic acceleration on Hexagon NPU when available.
- **Optional GPU path:** Offload selected workloads when a capable GPU is present.

## Tech Stack

- Python 3.11+
- PySide6 (UI)
- llama-cpp-python (local LLM)
- SQLite + sqlite-vec (memory)
- ONNX Runtime (embeddings)

## Roadmap

See `docs/ROADMAP.md`.

## License

MIT — see `LICENSE`.
