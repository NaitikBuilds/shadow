"""Simulate the observer loop and measure change-detection savings."""

import sys
import time

from shadow.config import change_detection_config, load_config
from shadow.perception import ChangeDetector


def main() -> int:
    cfg = load_config()
    ccfg = change_detection_config(cfg)

    detector = ChangeDetector(
        threshold=ccfg["threshold"],
        hash_size=ccfg["hash_size"],
        min_interval_ms=ccfg["min_interval_ms"],
    )

    print("Simulating observer loop: 10 checks over 10 seconds.")
    print("Keep your screen mostly idle to see unchanged results.")
    print()

    checks = 0
    changed_count = 0
    skipped_count = 0
    start = time.perf_counter()

    while checks < 10:
        time.sleep(1)
        checks += 1
        changed = detector.has_changed()
        if changed:
            changed_count += 1
            print(f"  [{checks:2d}] CHANGED")
        else:
            skipped_count += 1
            print(f"  [{checks:2d}] unchanged (would skip OCR)")

    elapsed = time.perf_counter() - start
    print()
    print(f"Total checks: {checks}")
    print(f"Changed:      {changed_count}")
    print(f"Unchanged:    {skipped_count}")
    print(f"Skip ratio:   {skipped_count / checks * 100:.0f}%")
    print(f"Elapsed:      {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
