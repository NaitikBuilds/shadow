"""Read the active window's UIA tree and extract paragraph text."""

import sys
import time

from shadow.perception import UIAutomationSource, UIATextExtractor

DELAY_SEC = 4


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

    # Rebuild UIANode from the dict
    from shadow.perception import UIANode

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

    root = from_dict(payload["root"])

    print()
    print("Window:", payload["window_title"])
    print("Process:", payload["process"])
    print()

    extractor = UIATextExtractor(max_chars=2000)
    result = extractor.extract(root)

    print(f"Blocks: {len(result['blocks'])}")
    print(f"Chars:  {result['char_count']}")
    print(f"Truncated: {result['truncated']}")
    print()
    print("--- extracted text ---")
    print(result["text"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
