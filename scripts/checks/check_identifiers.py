"""Extract URLs and file paths from the active window."""

import sys
import time

from shadow.perception import (
    IdentifierExtractor,
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
        is_offscreen=d.get("is_offscreen", False),
        bounding_rect=tuple(d.get("bounding_rect", (0, 0, 0, 0))),
        children=[from_dict(c) for c in d.get("children", [])],
    )


def main() -> int:
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

    extractor = IdentifierExtractor()
    ident = extractor.extract(
        process=payload.get("process", ""),
        title=payload.get("window_title", ""),
        root=root,
    )

    print()
    print("Window:", payload["window_title"][:80])
    print("Process:", payload["process"])
    print()
    print("URLs:    ", ident.urls or "(none)")
    print("Paths:   ", ident.paths or "(none)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
