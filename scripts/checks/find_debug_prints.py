"""Scan src/ for print() statements that should be removed.

Not every print is a bug. This tool flags them so you can review.
Whitelisted patterns (intentional prints) are excluded, and multi-line
print statements are checked by looking at a window of lines.
"""

import re
import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "shadow"

# Prints we intentionally keep. Matched against the print() line plus
# the next 5 lines (to catch multi-line print statements).
WHITELIST_PATTERNS = [
    r"\[calendar_winrt\]",  # documented no-op status
    r"\[shadow\]",  # shutdown warnings
    r"print\(tb",  # exception traceback to stderr
    r"traceback\.print_exc",  # explicit traceback dump
    r"file=sys\.stderr.*tb",  # traceback writes
]

# Patterns that always indicate leftover debug code.
DEBUG_PATTERNS = [
    r"\[observer\]",
    r"\[document\]",
    r"\[tick ",
    r"payload keys:",
    r"payload is None:",
    r"=== DEBUG ===",
]

LOOKAHEAD_LINES = 5


def _block_matches(lines: list[str], start: int, patterns: list[str]) -> bool:
    """Check the block starting at `start` for any whitelist pattern."""
    end = min(start + LOOKAHEAD_LINES, len(lines))
    block = "\n".join(lines[start:end])
    return any(re.search(p, block) for p in patterns)


def main() -> int:
    src_files = list(SRC_ROOT.rglob("*.py"))
    found_issues: list[tuple[Path, int, str]] = []
    info_prints: list[tuple[Path, int, str]] = []

    for path in src_files:
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if "print(" not in line:
                continue

            # Whitelisted (check block for multi-line patterns)
            if _block_matches(lines, i, WHITELIST_PATTERNS):
                info_prints.append((path, i + 1, line.strip()))
                continue

            # Always a debug print
            if any(re.search(p, line) for p in DEBUG_PATTERNS):
                found_issues.append((path, i + 1, line.strip()))
                continue

            # Unclassified print — warn
            found_issues.append((path, i + 1, line.strip()))

    if info_prints:
        print("Intentional prints (kept):")
        for path, i, line in info_prints:
            rel = path.relative_to(SRC_ROOT.parent.parent)
            print(f"  {rel}:{i}  {line}")
        print()

    if not found_issues:
        print("✓ No leftover debug prints found.")
        return 0

    print("⚠  Potential debug prints to review:")
    for path, i, line in found_issues:
        rel = path.relative_to(SRC_ROOT.parent.parent)
        print(f"  {rel}:{i}  {line}")
    print()
    print("Review each and either remove or add to WHITELIST_PATTERNS.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
