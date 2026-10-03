"""Extract interactive elements from the active window's UIA tree."""

import sys
import time

from shadow.config import interactive_config, load_config
from shadow.perception import (
    InteractiveExtractor,
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
        is_password=d.get("is_password", False),
        is_enabled=d.get("is_enabled", True),
        is_offscreen=d.get("is_offscreen", False),
        bounding_rect=tuple(d.get("bounding_rect", (0, 0, 0, 0))),
        children=[from_dict(c) for c in d.get("children", [])],
    )


def main() -> int:
    cfg = load_config()
    icfg = interactive_config(cfg)

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
    extractor = InteractiveExtractor(max_elements=icfg["max_elements"])
    result = extractor.extract(root)

    print()
    print("Window:", payload["window_title"][:80])
    print("Process:", payload["process"])
    print(f"Elements: {result['count']}")
    print("By role:", result["by_role"])
    print()

    for el in result["elements"][:20]:
        role = el["role"][:10]
        label = el["label"][:50]
        print(f"  [{role:<10}] {label}")
    if result["count"] > 20:
        print(f"  ... and {result['count'] - 20} more")

    return 0


if __name__ == "__main__":
    sys.exit(main())
