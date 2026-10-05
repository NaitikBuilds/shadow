"""Monitor awareness — enumerate displays and locate the active one.

Uses pywin32 (already a dependency) for reliable enumeration.
SHADOW uses this to:
  - Run UIA reads against the monitor containing the active window
  - Hash only the active monitor in change detection
  - Crop OCR captures to the active window's monitor
  - Future: region capture overlay spans all monitors
"""

import sys
from dataclasses import dataclass


@dataclass
class MonitorInfo:
    index: int
    left: int
    top: int
    right: int
    bottom: int
    work_left: int
    work_top: int
    work_right: int
    work_bottom: int
    is_primary: bool
    dpi_scale: float = 1.0

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        return (self.left, self.top, self.right, self.bottom)

    @property
    def work_area(self) -> tuple[int, int, int, int]:
        return (
            self.work_left,
            self.work_top,
            self.work_right,
            self.work_bottom,
        )

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def contains(self, x: int, y: int) -> bool:
        return self.left <= x < self.right and self.top <= y < self.bottom

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "bounds": list(self.bounds),
            "work_area": list(self.work_area),
            "is_primary": self.is_primary,
            "dpi_scale": self.dpi_scale,
            "width": self.width,
            "height": self.height,
        }


MONITORINFOF_PRIMARY = 0x1


def list_monitors() -> list[MonitorInfo]:
    """Return all monitors on the system.

    Returns an empty list on non-Windows or on failure.
    """
    if sys.platform != "win32":
        return []

    try:
        import win32api
    except ImportError:
        return []

    monitors: list[MonitorInfo] = []
    try:
        raw = win32api.EnumDisplayMonitors()
    except Exception:
        raw = []

    for idx, entry in enumerate(raw):
        try:
            hmon, _hdc, _rect = entry
            info = win32api.GetMonitorInfo(hmon)
        except Exception:
            continue

        rect = info.get("Monitor", (0, 0, 0, 0))
        work = info.get("Work", (0, 0, 0, 0))
        flags = info.get("Flags", 0)

        dpi_scale = _dpi_for_monitor(hmon)

        monitors.append(
            MonitorInfo(
                index=idx,
                left=int(rect[0]),
                top=int(rect[1]),
                right=int(rect[2]),
                bottom=int(rect[3]),
                work_left=int(work[0]),
                work_top=int(work[1]),
                work_right=int(work[2]),
                work_bottom=int(work[3]),
                is_primary=bool(flags & MONITORINFOF_PRIMARY),
                dpi_scale=dpi_scale,
            )
        )

    # Fallback: if enumeration returned nothing, synthesize from metrics
    if not monitors:
        try:
            user32 = __import__("ctypes").windll.user32
            width = user32.GetSystemMetrics(0)
            height = user32.GetSystemMetrics(1)
            if width > 0 and height > 0:
                monitors.append(
                    MonitorInfo(
                        index=0,
                        left=0,
                        top=0,
                        right=int(width),
                        bottom=int(height),
                        work_left=0,
                        work_top=0,
                        work_right=int(width),
                        work_bottom=int(height),
                        is_primary=True,
                        dpi_scale=1.0,
                    )
                )
        except Exception:
            pass

    return monitors


def active_monitor() -> MonitorInfo | None:
    """Return the monitor containing the foreground window."""
    if sys.platform != "win32":
        return None
    try:
        import win32gui

        hwnd = win32gui.GetForegroundWindow()
        rect = win32gui.GetWindowRect(hwnd)
    except Exception:
        return None

    cx = (rect[0] + rect[2]) // 2
    cy = (rect[1] + rect[3]) // 2

    for m in list_monitors():
        if m.contains(cx, cy):
            return m
    return None


def primary_monitor() -> MonitorInfo | None:
    for m in list_monitors():
        if m.is_primary:
            return m
    return None


def monitor_for_rect(
    rect: tuple[int, int, int, int],
) -> MonitorInfo | None:
    """Return the monitor containing the center of a rect."""
    cx = (rect[0] + rect[2]) // 2
    cy = (rect[1] + rect[3]) // 2
    for m in list_monitors():
        if m.contains(cx, cy):
            return m
    return None


# ---------- DPI ----------


def _dpi_for_monitor(hmon) -> float:
    """Return the DPI scale (1.0 = 96 dpi) for a monitor handle."""
    try:
        import ctypes

        shcore = ctypes.windll.shcore
    except Exception:
        return 1.0

    try:
        import ctypes

        dpi_x = ctypes.c_uint(0)
        dpi_y = ctypes.c_uint(0)
        # MDT_EFFECTIVE_DPI = 0
        shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
        if dpi_x.value > 0:
            return dpi_x.value / 96.0
    except Exception:
        pass
    return 1.0
