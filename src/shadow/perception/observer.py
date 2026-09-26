import hashlib
import json
import sys
import time

from PySide6.QtCore import QThread, Signal

from shadow.config import perception_config, source_enabled, tick_interval
from shadow.perception import ActiveWindowSource, ScreenOCRSource


class ObservationWorker(QThread):
    """Background loop that samples perception sources and writes to memory.

    Emits:
      tick(int)                — after each loop iteration
      observation(str, str)    — source name, short content preview
      skipped(str, str)        — reason, detail
      error(str)               — non-fatal error message
    """

    tick = Signal(int)
    observation = Signal(str, str)
    skipped = Signal(str, str)
    error = Signal(str)

    def __init__(self, memory, backend, config):
        super().__init__()
        self.memory = memory
        self.backend = backend
        self.config = config
        self.pcfg = perception_config(config)

        self.sources = []
        if source_enabled(config, "active_window"):
            self.sources.append(ActiveWindowSource())
        if source_enabled(config, "screen_ocr"):
            self.sources.append(ScreenOCRSource())

        self._tick_count = 0
        self._last_seen: dict[str, tuple[str, float]] = {}
        self._current_mode = (config.get("modes") or {}).get("default", "balanced")
        self._stopped = False

    def set_mode(self, mode: str) -> None:
        """Called from the UI thread; safe because it's a plain assignment."""
        self._current_mode = mode

    def stop(self) -> None:
        self._stopped = True
        self.requestInterruption()

    def run(self):
        while not self.isInterruptionRequested() and not self._stopped:
            try:
                self._do_tick()
            except Exception as exc:  # noqa: BLE001
                self.error.emit(str(exc))

            self._tick_count += 1
            self.tick.emit(self._tick_count)

            interval = tick_interval(self.config, self._current_mode)
            # Sleep in 100 ms slices so interruption is responsive
            slept = 0.0
            while slept < interval:
                if self.isInterruptionRequested() or self._stopped:
                    return
                self.msleep(100)
                slept += 0.1

    # ---------- internals ----------

    def _do_tick(self) -> None:
        if self._user_idle_too_long():
            self.skipped.emit("idle", f"user idle > {self.pcfg['idle_skip_sec']}s")
            return

        run_ocr = (
            self.pcfg["ocr_every_n_ticks"] > 0
            and self._tick_count % self.pcfg["ocr_every_n_ticks"] == 0
        )

        for source in self.sources:
            if not self.memory.get_consent(source.channel):
                continue
            if source.name == "screen_ocr" and not run_ocr:
                continue

            try:
                payload = source.sample()
            except Exception as exc:  # noqa: BLE001
                self.error.emit(f"{source.name} sample failed: {exc}")
                continue

            if payload is None:
                continue

            content = self._content_from(source.name, payload)
            if not content:
                continue

            if self._is_duplicate(source.name, content):
                continue

            rowid = self.memory.add_observation(
                source.name, content, metadata=json.dumps(payload, default=str)
            )
            try:
                vec = self.backend.embed(content)
                self.memory.add_embedding(rowid, vec)
            except Exception as exc:  # noqa: BLE001
                self.error.emit(f"embed failed for {source.name}: {exc}")

            preview = content[:120].replace("\n", " ")
            self.observation.emit(source.name, preview)

    def _content_from(self, source_name: str, payload: dict) -> str:
        if source_name == "active_window":
            title = (payload.get("title") or "").strip()
            process = (payload.get("process") or "").strip()
            if len(title) < self.pcfg["min_title_length"]:
                return ""
            title = title[: self.pcfg["max_title_length"]]
            return f"{process}: {title}" if process else title
        if source_name == "screen_ocr":
            return (payload.get("text") or "").strip()
        return ""

    def _is_duplicate(self, source_name: str, content: str) -> bool:
        h = hashlib.sha1(content.encode("utf-8", errors="ignore")).hexdigest()
        now = time.time()
        last = self._last_seen.get(source_name)
        if last and last[0] == h and (now - last[1]) < self.pcfg["dedupe_window_sec"]:
            return True
        self._last_seen[source_name] = (h, now)
        return False

    def _user_idle_too_long(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            import win32api

            last = win32api.GetLastInputInfo()
            elapsed_ms = win32api.GetTickCount() - last
            return elapsed_ms > self.pcfg["idle_skip_sec"] * 1000
        except Exception:
            return False
