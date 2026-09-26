import asyncio
import io
import sys
from datetime import datetime
from typing import Any

from .base import PerceptionSource


def _looks_like_real_text(text: str) -> bool:
    """Reject OCR output that's mostly symbols, mixed case chaos, or too short."""
    if not text or len(text.strip()) < 20:
        return False
    stripped = text.strip()
    total = len(stripped)
    alnum = sum(c.isalnum() or c.isspace() for c in stripped)
    if alnum / total < 0.65:
        return False
    letters = sum(c.isalpha() for c in stripped)
    if letters / total < 0.40:
        return False
    # Heuristic: too many isolated uppercase runs like "FullyQuaIifiedError"
    upper_runs = sum(1 for c in stripped if c.isupper())
    if upper_runs / max(letters, 1) > 0.35:
        return False
    return True


class ScreenOCRSource(PerceptionSource):
    """Captures the active window and extracts visible text via Windows OCR."""

    name = "screen_ocr"
    channel = "screen_capture"

    def __init__(self, max_chars: int = 4000):
        self.max_chars = max_chars

    def sample(self) -> dict[str, Any] | None:
        if sys.platform != "win32":
            return None
        try:
            text = asyncio.run(self._capture_and_ocr())
        except Exception:
            return None
        if not text or len(text.strip()) < 3:
            return None
        text = text.strip()[: self.max_chars]
        if not _looks_like_real_text(text):
            return None
        return {
            "text": text,
            "word_count": len(text.split()),
            "timestamp": datetime.utcnow().isoformat(sep=" ", timespec="seconds"),
        }

    async def _capture_and_ocr(self) -> str:
        try:
            from PIL import ImageGrab
            import win32gui
            from winrt.windows.globalization import Language
            from winrt.windows.graphics.imaging import BitmapDecoder
            from winrt.windows.media.ocr import OcrEngine
            from winrt.windows.storage.streams import (
                DataWriter,
                InMemoryRandomAccessStream,
            )
        except ImportError:
            return ""

        # 1. Grab the active window's pixels
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return ""
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        except Exception:
            return ""

        if right <= left or bottom <= top:
            return ""

        try:
            img = ImageGrab.grab(bbox=(left, top, right, bottom))
        except Exception:
            return ""

        # 2. Encode PNG into memory
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        # 3. Bridge: bytes -> WinRT stream
        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream.get_output_stream_at(0))
        writer.write_bytes(png_bytes)
        await writer.store_async()
        writer.detach_stream()
        stream.seek(0)

        # 4. Decode PNG into a SoftwareBitmap
        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()

        # 5. Run OCR
        engine = OcrEngine.try_create_from_language(Language("en-US"))
        if engine is None:
            engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            return ""

        result = await engine.recognize_async(bitmap)
        if result is None:
            return ""
        return result.text or ""
