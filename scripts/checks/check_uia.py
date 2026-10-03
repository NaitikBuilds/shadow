"""Read the UIA tree of the active window and print a summary."""

import sys

from shadow.config import load_config, uia_config
from shadow.perception import UIAutomationSource


def main() -> int:
    cfg = load_config()
    ucfg = uia_config(cfg)

    src = UIAutomationSource(
        max_depth=ucfg["max_depth"],
        max_elements=ucfg["max_elements"],
        min_useful_nodes=ucfg["min_useful_nodes"],
    )

    print("Focus your target window, then press Enter.")
    input()

    payload = src.sample()
    if payload is None:
        print("No UIA data returned. Is uiautomation installed?")
        print("Focused window must be a real app, not SHADOW.")
        return 1

    print()
    print("Window title:", payload["window_title"])
    print("Process:", payload["process"])
    print("Nodes:", payload["node_count"])
    print("Max depth reached:", payload["max_depth_reached"])
    print()

    def print_tree(node, depth=0):
        if node is None:
            return
        indent = "  " * depth
        text = node.get("name", "")[:60]
        ctype = node.get("control_type", "")
        print(f"{indent}[{ctype}] {text}")
        for child in node.get("children", [])[:5]:
            print_tree(child, depth + 1)

    print_tree(payload["root"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
