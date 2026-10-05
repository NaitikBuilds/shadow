"""Print information about all monitors on the system."""

import sys

from shadow.perception import (
    active_monitor,
    list_monitors,
    primary_monitor,
)


def main() -> int:
    monitors = list_monitors()
    print(f"Monitors detected: {len(monitors)}")
    print()

    for m in monitors:
        marker = " (primary)" if m.is_primary else ""
        print(f"  [{m.index}]{marker}")
        print(f"    Bounds:   {m.bounds}  {m.width}x{m.height}")
        print(f"    Work:     {m.work_area}")
        print(f"    DPI:      {m.dpi_scale:.2f} ({int(m.dpi_scale * 96)} DPI)")
        print()

    am = active_monitor()
    if am:
        print(f"Active monitor: [{am.index}] at {am.bounds}")
    else:
        print("Active monitor: (none — no foreground window?)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
