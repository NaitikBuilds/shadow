"""Measure UIA vs OCR on the same active window.

Captures the active window and runs both extraction paths, timing each.
Appends one JSON line per run to benchmarks/uia_vs_ocr.jsonl.

Usage:
    python scripts/checks/compare_uia_ocr.py
    python scripts/checks/compare_uia_ocr.py --summary
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from shadow.perception import (  # noqa: E402
    ActiveWindowSource,
    ScreenOCRSource,
    UIANode,
    UIATextExtractor,
    UIAutomationSource,
    WindowClassifier,
)

RESULTS_PATH = Path(__file__).resolve().parents[2] / "benchmarks" / "uia_vs_ocr.jsonl"

DELAY_SEC = 4


def from_dict(d):
    return UIANode(
        name=d.get("name", ""),
        control_type=d.get("control_type", ""),
        automation_id=d.get("automation_id", ""),
        class_name=d.get("class_name", ""),
        value=d.get("value", ""),
        is_password=d.get("is_password", False),
        is_enabled=d.get("is_enabled", True),
        is_selected=d.get("is_selected", False),
        is_offscreen=d.get("is_offscreen", False),
        bounding_rect=tuple(d.get("bounding_rect", (0, 0, 0, 0))),
        children=[from_dict(c) for c in d.get("children", [])],
    )


def run_once() -> dict | None:
    window = ActiveWindowSource().sample()
    if not window:
        print("No active window.")
        return None

    process = window.get("process", "")
    title = window.get("title", "")

    classifier = WindowClassifier()
    profile = classifier.classify(process=process, title=title)

    print(f"Window: {process} — {title[:60]}")
    print(f"Category: {profile.category.value}")
    print()

    # --- UIA ---
    uia_ms = 0.0
    uia_chars = 0
    uia_blocks = 0
    if profile.use_uia:
        uia_src = UIAutomationSource()
        t0 = time.perf_counter()
        payload = uia_src.sample()
        uia_ms = (time.perf_counter() - t0) * 1000
        if payload:
            root = from_dict(payload["root"])
            text_result = UIATextExtractor().extract(root)
            uia_chars = text_result.get("char_count", 0)
            uia_blocks = len(text_result.get("blocks", []))

    # --- OCR ---
    ocr_ms = 0.0
    ocr_chars = 0
    ocr_words = 0
    if profile.use_ocr:
        ocr_src = ScreenOCRSource()
        t0 = time.perf_counter()
        payload = ocr_src.sample()
        ocr_ms = (time.perf_counter() - t0) * 1000
        if payload:
            ocr_chars = len(payload.get("text", ""))
            ocr_words = payload.get("word_count", 0)

    winner = "uia" if uia_chars > ocr_chars else "ocr"
    if uia_chars == 0 and ocr_chars == 0:
        winner = "none"

    result = {
        "timestamp": datetime.utcnow().isoformat(sep=" ", timespec="seconds"),
        "process": process,
        "title": title[:120],
        "category": profile.category.value,
        "uia_ms": round(uia_ms, 1),
        "uia_chars": uia_chars,
        "uia_blocks": uia_blocks,
        "ocr_ms": round(ocr_ms, 1),
        "ocr_chars": ocr_chars,
        "ocr_words": ocr_words,
        "winner": winner,
    }
    return result


def print_result(result: dict) -> None:
    print(
        f"UIA: {result['uia_ms']:>7.1f} ms  "
        f"{result['uia_chars']:>5} chars  "
        f"{result['uia_blocks']:>3} blocks"
    )
    print(
        f"OCR: {result['ocr_ms']:>7.1f} ms  "
        f"{result['ocr_chars']:>5} chars  "
        f"{result['ocr_words']:>3} words"
    )
    print(f"Winner: {result['winner']}")


def append_result(result: dict) -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(result) + "\n")


def print_summary() -> int:
    if not RESULTS_PATH.exists():
        print("No results yet. Run without --summary first.")
        return 1

    lines = RESULTS_PATH.read_text(encoding="utf-8").strip().splitlines()
    runs = [json.loads(line) for line in lines if line.strip()]

    if not runs:
        print("No runs recorded.")
        return 1

    # Aggregate by category
    by_cat: dict[str, dict] = {}
    for r in runs:
        cat = r["category"]
        bucket = by_cat.setdefault(
            cat,
            {
                "runs": 0,
                "uia_ms_total": 0.0,
                "uia_chars_total": 0,
                "ocr_ms_total": 0.0,
                "ocr_chars_total": 0,
                "uia_wins": 0,
                "ocr_wins": 0,
            },
        )
        bucket["runs"] += 1
        bucket["uia_ms_total"] += r["uia_ms"]
        bucket["uia_chars_total"] += r["uia_chars"]
        bucket["ocr_ms_total"] += r["ocr_ms"]
        bucket["ocr_chars_total"] += r["ocr_chars"]
        if r["winner"] == "uia":
            bucket["uia_wins"] += 1
        elif r["winner"] == "ocr":
            bucket["ocr_wins"] += 1

    print(f"Total runs: {len(runs)}")
    print()
    print(
        f"{'category':<12} {'runs':>4} "
        f"{'avg UIA ms':>11} {'avg UIA chars':>14} "
        f"{'avg OCR ms':>11} {'avg OCR chars':>14} "
        f"{'UIA wins':>9} {'OCR wins':>9}"
    )
    print("-" * 92)
    for cat, b in sorted(by_cat.items()):
        n = b["runs"]
        print(
            f"{cat:<12} {n:>4} "
            f"{b['uia_ms_total']/n:>11.1f} "
            f"{b['uia_chars_total']//n:>14} "
            f"{b['ocr_ms_total']/n:>11.1f} "
            f"{b['ocr_chars_total']//n:>14} "
            f"{b['uia_wins']:>9} {b['ocr_wins']:>9}"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    if args.summary:
        return print_summary()

    print(f"Switch to your target window. Reading in {DELAY_SEC}s...")
    for i in range(DELAY_SEC, 0, -1):
        print(f"  {i}...")
        time.sleep(1)

    result = run_once()
    if result is None:
        return 1

    print_result(result)
    append_result(result)
    print()
    print(f"Appended to {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
