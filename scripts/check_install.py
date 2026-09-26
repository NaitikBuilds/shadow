"""Confirm `shadow` is loading from the source tree, not site-packages."""

import shadow
from pathlib import Path

src_root = Path(__file__).resolve().parents[1] / "src"
loaded_from = Path(shadow.__file__).resolve()

print(f"Loaded from: {loaded_from}")

if str(loaded_from).startswith(str(src_root)):
    print("✓ Editable install is active.")
else:
    print("✗ Stale copy detected in site-packages.")
    print('  Fix: pip uninstall shadow -y && pip install -e ".[dev]"')
    raise SystemExit(1)
