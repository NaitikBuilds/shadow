"""Check what the StuckDetector finds in your recent activity."""

import sys

from shadow.agent import StuckDetector
from shadow.config import load_config
from shadow.memory import MemoryStore


def main() -> int:
    cfg = load_config()
    store = MemoryStore(cfg["memory"]["db_path"])
    try:
        detector = StuckDetector(store, cfg)
        insights = detector.find_stuck(limit=5)

        if not insights:
            print("No stuck patterns detected in recent activity.")
            return 0

        print(f"Found {len(insights)} stuck patterns:")
        print()
        for i in insights:
            print(f"  [{i.kind}] {i.title}")
            print(f"    {i.body}")
            print(f"    score {i.score:.2f}")
            print()
    finally:
        store.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
