"""Verify that core SHADOW modules make no network calls.

FR-NET-01: The main process must make zero network calls in v1.0.

This script scans src/shadow/ for imports of common network libraries.
Any match outside the whitelist fails with exit code 1.

Whitelist:
  - src/shadow/models/manager.py  (downloads models — network is the point)
  - src/shadow/cloud/**           (Post-v1.0, isolated by design)
"""

import ast
import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src" / "shadow"

NETWORK_MODULES = {
    "requests",
    "urllib",
    "urllib2",
    "urllib3",
    "http",
    "socket",
    "aiohttp",
    "httpx",
    "websocket",
    "websockets",
    "ftplib",
    "smtplib",
    "telnetlib",
}

WHITELIST = {
    "models/manager.py",
}

WHITELIST_PREFIXES = ("cloud/",)


def is_whitelisted(rel_path: str) -> bool:
    if rel_path in WHITELIST:
        return True
    return any(rel_path.startswith(p) for p in WHITELIST_PREFIXES)


def module_imports(path: Path) -> set[str]:
    """Return the set of top-level module names imported in a Python file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, OSError):
        return set()

    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    return imports


def check() -> int:
    violations: list[tuple[str, set[str]]] = []
    for py_file in SRC_ROOT.rglob("*.py"):
        rel = str(py_file.relative_to(SRC_ROOT)).replace("\\", "/")
        if is_whitelisted(rel):
            continue
        bad = module_imports(py_file) & NETWORK_MODULES
        if bad:
            violations.append((rel, bad))

    if not violations:
        print("✓ Network isolation check passed.")
        print(f"  Scanned: {SRC_ROOT}")
        print(f"  Whitelisted: {sorted(WHITELIST) + list(WHITELIST_PREFIXES)}")
        return 0

    print("✗ Network isolation violated.")
    print("  The following files import network modules outside the whitelist:")
    for rel, mods in violations:
        print(f"    {rel}: {sorted(mods)}")
    print()
    print("  If this is intentional, add the file to WHITELIST in this script.")
    return 1


if __name__ == "__main__":
    sys.exit(check())
