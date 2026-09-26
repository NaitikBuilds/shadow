import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from .base import PerceptionSource


@dataclass
class ActiveWindow:
    title: str
    process: str
    pid: int
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ActiveWindowSource(PerceptionSource):
    """Reads the title and process of the currently focused window."""

    name = "active_window"
    channel = "screen_capture"

    def sample(self) -> dict[str, Any] | None:
        if sys.platform != "win32":
            return None

        try:
            import psutil
            import win32gui
            import win32process
        except ImportError:
            return None

        try:
            hwnd = win32gui.GetForegroundWindow()
        except Exception:
            return None

        if not hwnd:
            return None

        try:
            title = win32gui.GetWindowText(hwnd) or ""
        except Exception:
            title = ""

        process_name = ""
        pid = 0
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid:
                proc = psutil.Process(pid)
                process_name = proc.name()
        except Exception:
            process_name = ""

        # Skip empty/system windows — no useful signal
        if not title and not process_name:
            return None

        payload = ActiveWindow(
            title=title.strip(),
            process=process_name.strip(),
            pid=int(pid),
            timestamp=datetime.utcnow().isoformat(sep=" ", timespec="seconds"),
        )
        return payload.to_dict()
