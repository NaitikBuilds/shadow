"""Measure SHADOW performance and append to benchmarks/results.jsonl.

Measures:
  - Model load time (chat + embedder)
  - Chat first-token latency
  - Chat full-response time (fixed token count)
  - Embedding latency (single sentence)

Usage:
    python scripts/run_benchmarks.py            # append new result
    python scripts/run_benchmarks.py --compare  # compare vs previous
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shadow.config import load_config  # noqa: E402
from shadow.hal.cpu_backend import CpuBackend  # noqa: E402

RESULTS_PATH = Path(__file__).resolve().parents[1] / "benchmarks" / "results.jsonl"


def measure() -> dict:
    cfg = load_config()

    t0 = time.perf_counter()
    backend = CpuBackend(
        model_path=cfg["model"]["path"],
        n_ctx=cfg["model"]["n_ctx"],
        n_threads=cfg["model"].get("n_threads") or None,
        n_gpu_layers=cfg["model"]["n_gpu_layers"],
        embedder_model=cfg["model"].get("embedder_model"),
        embedder_tokenizer=cfg["model"].get("embedder_tokenizer"),
    )
    load_time = time.perf_counter() - t0

    prompt = "In one short sentence, what is a knowledge graph?"

    t1 = time.perf_counter()
    first_token_at = None
    tokens = 0
    for _chunk in backend.generate_stream(prompt, max_tokens=64):
        if first_token_at is None:
            first_token_at = time.perf_counter() - t1
        tokens += 1
    full_time = time.perf_counter() - t1

    embed_t0 = time.perf_counter()
    backend.embed("This is a benchmark sentence for embedding latency.")
    embed_time = time.perf_counter() - embed_t0

    return {
        "timestamp": datetime.utcnow().isoformat(sep=" ", timespec="seconds"),
        "model_load_sec": round(load_time, 3),
        "first_token_sec": round(first_token_at or 0.0, 3),
        "full_response_sec": round(full_time, 3),
        "tokens_generated": tokens,
        "tokens_per_sec": round(tokens / full_time, 2) if full_time > 0 else 0.0,
        "embed_latency_ms": round(embed_time * 1000, 1),
    }


def compare(new: dict, old: dict) -> int:
    """Return 1 if a >15% regression is found, else 0."""
    fields = [
        "model_load_sec",
        "first_token_sec",
        "full_response_sec",
        "embed_latency_ms",
    ]
    regressions = []
    for field in fields:
        prev = old.get(field)
        cur = new.get(field)
        if prev and cur and cur > prev * 1.15:
            pct = (cur / prev - 1) * 100
            regressions.append(f"  {field}: {prev} → {cur} (+{pct:.1f}%)")

    if regressions:
        print("✗ Performance regression detected:")
        print("\n".join(regressions))
        return 1

    print("✓ No regression > 15%.")
    return 0


def last_result() -> dict | None:
    if not RESULTS_PATH.exists():
        return None
    lines = RESULTS_PATH.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        return None
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--compare", action="store_true", help="Compare against the last saved result."
    )
    args = parser.parse_args()

    print("Running benchmark...")
    result = measure()

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(result) + "\n")

    print()
    print("Results:")
    for k, v in result.items():
        print(f"  {k:<22} {v}")

    if args.compare:
        prev = last_result()
        if prev and prev["timestamp"] != result["timestamp"]:
            return compare(result, prev)

    return 0


if __name__ == "__main__":
    sys.exit(main())
