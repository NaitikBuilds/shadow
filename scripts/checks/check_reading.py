"""Read position from the active window and show resume suggestion."""

import sys
import time

from shadow.config import load_config
from shadow.memory import MemoryStore
from shadow.perception import (
    ReadingPositionTracker,
    UIANode,
    UIAutomationSource,
)

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


def main() -> int:
    cfg = load_config()

    print(f"Open a document and scroll a bit. Reading in {DELAY_SEC}s...")
    for i in range(DELAY_SEC, 0, -1):
        print(f"  {i}...")
        time.sleep(1)

    src = UIAutomationSource()
    payload = src.sample()
    if payload is None:
        print("Could not read active window.")
        return 1

    root = from_dict(payload["root"])

    store = MemoryStore(cfg["memory"]["db_path"])
    try:
        tracker = ReadingPositionTracker(store, cfg)
        pos = tracker.record(
            process=payload.get("process", ""),
            title=payload.get("window_title", ""),
            root=root,
        )
        print()
        if pos is None:
            print("No position recorded (no identifier or no scroll bar).")
            return 0
        print(f"Identifier: {pos.identifier}")
        print(f"Title:      {pos.title[:80]}")
        print(f"Position:   {pos.position_pct:.1f}%")
        print(f"Section:    {pos.section or '(none)'}")
        print()
        print("Resume hint:", tracker.resume_suggestion(pos.identifier))
    finally:
        store.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
