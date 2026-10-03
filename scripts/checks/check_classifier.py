"""Classify the currently focused window.

Waits N seconds, then reads whatever window has focus. This gives you
time to switch to the target window after starting the script.
"""

import sys
import time

from shadow.config import load_config, window_classifier_config
from shadow.perception import UIAutomationSource, WindowClassifier

DELAY_SEC = 4


def main() -> int:
    cfg = load_config()
    wcfg = window_classifier_config(cfg)
    classifier = WindowClassifier(custom_map=wcfg["custom_map"])

    print(f"Switch to your target window now. Reading in {DELAY_SEC}s...")
    for i in range(DELAY_SEC, 0, -1):
        print(f"  {i}...")
        time.sleep(1)

    src = UIAutomationSource()
    payload = src.sample()
    if payload is None:
        print("Could not read active window.")
        return 1

    profile = classifier.classify(
        process=payload.get("process", ""),
        title=payload.get("window_title", ""),
        class_name="",
    )

    print()
    print("Process:      ", profile.process)
    print("Title:        ", profile.title[:80])
    print("Category:     ", profile.category.value)
    print("Use UIA:      ", profile.use_uia)
    print("Use OCR:      ", profile.use_ocr)
    print("Extract URL:  ", profile.extract_url)
    print("Extract path: ", profile.extract_path)
    print("Is SHADOW:    ", profile.is_self)
    print("Notes:        ", ", ".join(profile.notes) or "(none)")

    if profile.extract_url:
        url = classifier.extract_url_from_title(profile.title)
        if url:
            print("Detected URL: ", url)
    if profile.extract_path:
        path = classifier.extract_path_from_title(profile.title)
        if path:
            print("Detected path:", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
