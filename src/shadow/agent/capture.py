"""Quick Capture — global hotkey saves current screen context as a note.

Triggered by the user (Ctrl+Shift+S by default), not by observation.
Captures the active window's title and OCR text, writes a markdown file
to a workspace folder, and records an observation so the capture is
retrievable through normal memory queries.

No new consent channel — this is a user action, like clicking a button.
"""

import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path


class QuickCapture:
    """Global hotkey listener that captures current screen context."""

    def __init__(self, memory, config):
        self.memory = memory
        self.config = config
        self.cfg = config.get("capture") or {}

        self.enabled = bool(self.cfg.get("enabled", True))
        self.hotkey = str(self.cfg.get("hotkey", "<ctrl>+<shift>+s"))
        self.output_dir = Path(
            str(self.cfg.get("output_dir", "~/SHADOW_workspace/captures"))
        ).expanduser()

        self._listener = None
        self.on_capture: Callable[[str], None] | None = None

    # ---------- lifecycle ----------

    def start(self) -> None:
        """Begin listening for the hotkey. Safe to call multiple times."""
        if not self.enabled or sys.platform != "win32":
            return
        if self._listener is not None:
            return

        try:
            from pynput import keyboard
        except ImportError:
            return

        try:
            self._listener = keyboard.GlobalHotKeys(
                {
                    self.hotkey: self._on_hotkey,
                }
            )
            self._listener.daemon = True
            self._listener.start()
        except Exception:
            self._listener = None

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

    # ---------- hotkey handler ----------

    def _on_hotkey(self) -> None:
        try:
            path = self.capture_once()
        except Exception:
            path = None

        if path and self.on_capture is not None:
            try:
                self.on_capture(str(path))
            except Exception:
                pass

    # ---------- core capture ----------

    def capture_once(self) -> Path | None:
        """Grab current context, write markdown, record observation."""
        timestamp = datetime.utcnow()
        window = self._read_active_window()
        ocr_text = self._read_ocr_text()

        if not window and not ocr_text:
            return None

        self.output_dir.mkdir(parents=True, exist_ok=True)
        filename = timestamp.strftime("%Y-%m-%d_%H-%M-%S") + ".md"
        path = self.output_dir / filename

        markdown = self._build_markdown(timestamp, window, ocr_text)
        path.write_text(markdown, encoding="utf-8")

        self._record_observation(timestamp, window, ocr_text, path)
        return path

    # ---------- readers ----------

    def _read_active_window(self) -> dict | None:
        try:
            from shadow.perception.active_window import ActiveWindowSource

            return ActiveWindowSource().sample()
        except Exception:
            return None

    def _read_ocr_text(self) -> str:
        try:
            from shadow.perception.screen_ocr import ScreenOCRSource

            payload = ScreenOCRSource().sample()
            if payload:
                return (payload.get("text") or "").strip()
        except Exception:
            pass
        return ""

    # ---------- writers ----------

    def _build_markdown(
        self,
        timestamp: datetime,
        window: dict | None,
        ocr_text: str,
    ) -> str:
        lines = ["# Quick Capture", ""]
        lines.append(f"**Captured:** {timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC")

        if window:
            title = (window.get("title") or "").strip()
            process = (window.get("process") or "").strip()
            if title or process:
                source = f"{process} — {title}" if process else title
                lines.append(f"**Source:** {source}")
        lines.append("")

        lines.append("## Content")
        lines.append("")
        if ocr_text:
            lines.append(ocr_text)
        else:
            lines.append("_No visible text was captured._")
        lines.append("")
        return "\n".join(lines)

    def _record_observation(
        self,
        timestamp: datetime,
        window: dict | None,
        ocr_text: str,
        path: Path,
    ) -> None:
        title = (window or {}).get("title") or ""
        process = (window or {}).get("process") or ""
        preview = ocr_text[:500] if ocr_text else ""
        content = f"Quick capture saved to {path.name}"
        if process or title:
            content += f"\nWindow: {process} — {title}".rstrip(" —")
        if preview:
            content += f"\n\n{preview}"

        try:
            self.memory.add_observation(
                "capture",
                content,
                metadata=f'{{"path": "{path.as_posix()}"}}',
            )
        except Exception:
            pass
