"""Read and track tabs from the active window."""

import sys
import time

from shadow.config import load_config, tabs_config
from shadow.perception import (
    TabReader,
    TabStateTracker,
    UIANode,
    UIAutomationSource,
)

DELAY_SEC = 4


def from_dict(d):
    return UIANode(
        name=d["name"],
        control_type=d["control_type"],
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
    tcfg = tabs_config(cfg)

    print(f"Switch to your target window now. Reading in {DELAY_SEC}s...")
    for i in range(DELAY_SEC, 0, -1):
        print(f"  {i}...")
        time.sleep(1)

    src = UIAutomationSource()
    payload = src.sample()
    if payload is None:
        print("Could not read active window.")
        return 1

    root = from_dict(payload["root"])
    reader = TabReader()
    tabs = reader.extract(root)

    print()
    print("Window:", payload["window_title"][:80])
    print("Process:", payload["process"])
    print(f"Tabs found: {len(tabs)}")
    for tab in tabs:
        marker = " *" if tab.is_active else "  "
        print(f"  {marker} [{tab.order}] {tab.title[:80]}")

    if not tabs:
        return 0

    from shadow.memory import MemoryStore

    store = MemoryStore(cfg["memory"]["db_path"])
    try:
        tracker = TabStateTracker(store)
        tracker.record(payload["process"], tabs)

        stale = tracker.stale_tabs(
            process=payload["process"],
            stale_hours=tcfg["stale_hours"],
        )
        if stale:
            print()
            print(f"Stale tabs ({len(stale)}):")
            for s in stale:
                print(f"  {s.title[:60]} ({s.hours_open:.1f}h)")

        related = tracker.related_tabs(
            process=payload["process"],
            min_overlap=tcfg["related_min_overlap"],
        )
        if related:
            print()
            print("Related groups:")
            for g in related:
                print(f"  '{g.keyword}': {len(g.tabs)} tabs")
    finally:
        store.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
