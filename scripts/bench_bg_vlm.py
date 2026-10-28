"""G1 benchmark: Florence-2 vs Moondream2 for background captions.

Run on target hardware (Intel i5 12th Gen, 16 GB, Balanced mode).
Produces docs/design/phase4_g1_vlm_results.md (table filled in manually).
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import statistics
import time
from pathlib import Path

IMAGES_DIR = Path("scripts/bench_images")
OUT = Path("scripts/bench_results.json")

# Fill these with your actual adapters (reuse Phase 3.6 VLM interface).
ADAPTERS = {
    "florence2": "shadow.hal.vision.florence2_backend.Florence2Backend",
    "moondream2": "shadow.hal.vision.moondream_backend.Moondream2Backend",
}


def rss_mb() -> float:
    # Linux/macOS; on Windows use psutil.Process().memory_info().rss
    try:
        import psutil

        return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
    except Exception:
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def bench(adapter_name: str, image_paths: list[Path]) -> dict:
    import importlib

    module_path, cls_name = ADAPTERS[adapter_name].rsplit(".", 1)
    Backend = getattr(importlib.import_module(module_path), cls_name)

    base_rss = rss_mb()
    t0 = time.perf_counter()
    backend = Backend()
    backend.load()  # cold load
    load_s = time.perf_counter() - t0
    loaded_rss = rss_mb()

    latencies = []
    captions = []
    for p in image_paths:
        frame = backend.capture_from_file(p)  # your existing reader
        t = time.perf_counter()
        cap = backend.caption(frame)  # same call the registry will use
        latencies.append(time.perf_counter() - t)
        captions.append(cap)

    t = time.perf_counter()
    backend.unload()
    unload_s = time.perf_counter() - t

    return {
        "adapter": adapter_name,
        "load_s": round(load_s, 3),
        "unload_s": round(unload_s, 3),
        "rss_delta_mb": round(loaded_rss - base_rss, 1),
        "latency_p50_s": round(statistics.median(latencies), 3),
        "latency_p95_s": round(sorted(latencies)[int(0.95 * len(latencies)) - 1], 3),
        "captions": captions,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", default=str(IMAGES_DIR))
    args = ap.parse_args()
    paths = sorted(Path(args.images).glob("*.png"))
    if not paths:
        raise SystemExit(f"no images in {args.images}")
    results = [bench(name, paths) for name in ADAPTERS]
    OUT.write_text(json.dumps(results, indent=2))
    print(f"wrote {OUT}")
    # CPU sampling is done externally (e.g. Windows Performance Recorder)
    # because it needs a stable 30 s window per mode; see report template.


if __name__ == "__main__":
    main()
