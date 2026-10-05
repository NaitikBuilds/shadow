"""Simulate adaptive cadence with real change detection."""

import sys
import time

from shadow.config import load_config
from shadow.perception import AdaptiveCadence, ChangeDetector


def main() -> int:
    cfg = load_config()
    detector = ChangeDetector(min_interval_ms=200)
    cadence = AdaptiveCadence(detector, cfg)

    print("Adaptive cadence simulation for 60 seconds.")
    print("Move or scroll a window to see the interval shrink.")
    print("Leave the screen idle to see it grow.")
    print()

    start = time.perf_counter()
    samples = 0
    while time.perf_counter() - start < 60:
        if cadence.due():
            changed, next_interval = cadence.sample()
            samples += 1
            marker = "CHANGED" if changed else "same   "
            elapsed = time.perf_counter() - start
            print(
                f"  [{elapsed:5.1f}s] #{samples:3d} {marker} "
                f"next poll in {next_interval}s"
            )
        time.sleep(0.5)

    info = cadence.info()
    print()
    print(f"Total samples: {info.total_samples}")
    print(f"Changed:       {info.changed_count}")
    print(f"Final interval: {info.current_interval}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
