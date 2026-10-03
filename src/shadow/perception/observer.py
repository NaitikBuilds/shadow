import hashlib
import json
import sys
import time

from PySide6.QtCore import QThread, Signal

from shadow.config import perception_config, redaction_config, source_enabled
from shadow.memory import EntityExtractor, GraphBuilder
from shadow.memory.redaction import Redactor
from shadow.perception.active_window import ActiveWindowSource
from shadow.perception.budget import BudgetController
from shadow.perception.calendar import CalendarSource
from shadow.perception.calendar_winrt import WindowsCalendarSource
from shadow.perception.clipboard import ClipboardSource
from shadow.perception.documents import DocumentSource
from shadow.perception.screen_ocr import ScreenOCRSource
from shadow.perception.typing import TypingDynamicsSource


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
        rcfg = redaction_config(config)
        self.redactor = Redactor(
            enabled=rcfg["enabled"],
            redact_emails=rcfg["redact_emails"],
            placeholder=rcfg["placeholder"],
        )
        self.budget = BudgetController(memory, config)

        self.sources = []
        if source_enabled(config, "active_window"):
            self.sources.append(ActiveWindowSource())
        if source_enabled(config, "screen_ocr"):
            self.sources.append(ScreenOCRSource())
        if source_enabled(config, "typing_dynamics"):
            tcfg = self.pcfg.get("typing") or {}
            self.sources.append(
                TypingDynamicsSource(
                    pause_threshold_sec=tcfg.get("pause_threshold_sec", 2.0),
                    min_keystrokes=tcfg.get("min_keystrokes", 10),
                )
            )

        if source_enabled(config, "document_watch"):
            dcfg = self.pcfg.get("documents") or {}
            self.sources.append(
                DocumentSource(
                    watch_folders=dcfg.get("watch_folders") or [],
                    extensions=dcfg.get("extensions")
                    or [".txt", ".md", ".pdf", ".docx"],
                    max_file_size_mb=dcfg.get("max_file_size_mb", 5),
                    max_chars=dcfg.get("max_chars", 4000),
                )
            )

        if source_enabled(config, "calendar"):
            ccfg = self.pcfg.get("calendar") or {}
            # Preferred: native Windows consolidated calendar store.
            # Requires MSIX packaging for the 'appointments' capability.
            # Gracefully no-ops when permission is unavailable.
            self.sources.append(
                WindowsCalendarSource(
                    lookback_days=ccfg.get("lookback_days", 1),
                    lookahead_days=ccfg.get("lookahead_days", 14),
                )
            )
            # Fallback: .ics files in watched folders.
            self.sources.append(
                CalendarSource(
                    watch_folders=ccfg.get("watch_folders") or [],
                    lookback_days=ccfg.get("lookback_days", 1),
                    lookahead_days=ccfg.get("lookahead_days", 14),
                )
            )

        if source_enabled(config, "clipboard"):
            self.sources.append(ClipboardSource())

        self.graph_builder: GraphBuilder | None = None
        ee_cfg = self.pcfg.get("entity_extraction") or {}
        if ee_cfg.get("enabled", True):
            extractor = EntityExtractor(
                known_projects=ee_cfg.get("known_projects") or []
            )
            self.graph_builder = GraphBuilder(self.memory, extractor)

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
        for source in self.sources:
            try:
                source.stop()
            except Exception:  # noqa: BLE001
                pass

    def run(self):
        while not self.isInterruptionRequested() and not self._stopped:
            try:
                self._do_tick()
            except Exception as exc:  # noqa: BLE001
                self.error.emit(str(exc))

            self._tick_count += 1
            self.tick.emit(self._tick_count)

            interval = self.budget.effective_interval(self._current_mode)
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

            # Redact secrets before storage or embedding.
            try:
                content, matched = self.redactor.redact(content)
                if matched:
                    self.error.emit(
                        f"redaction in {source.name}: {len(matched)} secret(s) removed"
                    )
            except Exception:
                matched = []

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

            if self.graph_builder is not None:
                try:
                    self.graph_builder.process(rowid, content)
                except Exception as exc:  # noqa: BLE001
                    self.error.emit(f"graph build failed for {source.name}: {exc}")

            preview = content[:120].replace("\n", " ")
            self.observation.emit(source.name, preview)

    def _content_from(self, source_name: str, payload: dict) -> str:
        # Never observe ourselves.
        process = (payload.get("process") or "").lower()
        title = (payload.get("title") or "").lower()
        if "python" in process and "shadow" in title:
            return ""
        if "shadow" in title and "silent on-device" in title:
            return ""
        if source_name == "screen_ocr":
            text_lower = (payload.get("text") or "").lower()
            if "silent on-device life context agent" in text_lower:
                return ""

        if source_name == "active_window":
            title = (payload.get("title") or "").strip()
            process = (payload.get("process") or "").strip()
            if len(title) < self.pcfg["min_title_length"]:
                return ""
            title = title[: self.pcfg["max_title_length"]]
            return f"{process}: {title}" if process else title
        if source_name == "screen_ocr":
            return (payload.get("text") or "").strip()
        if source_name == "typing_dynamics":
            return (payload.get("summary") or "").strip()
        if source_name == "document":
            name = (payload.get("name") or "").strip()
            text = (payload.get("text") or "").strip()
            if not name or not text:
                return ""
            return f"Document: {name}\n{text}"
        if source_name in ("calendar", "calendar_winrt"):
            return (payload.get("content") or "").strip()
        if source_name == "clipboard":
            text = (payload.get("content") or "").strip()
            if len(text) < 10:
                return ""
            preview = text[:500]
            return f"Clipboard ({payload.get('chars', 0)} chars):\n{preview}"
        return ""

    def _is_duplicate(self, source_name: str, content: str) -> bool:
        now = time.time()
        exact = hashlib.sha1(content.encode("utf-8", errors="ignore")).hexdigest()
        fuzzy = hashlib.sha1(content[:80].encode("utf-8", errors="ignore")).hexdigest()

        last_exact = self._last_seen.get(f"{source_name}:exact")
        if last_exact and last_exact[0] == exact:
            if now - last_exact[1] < self.pcfg["dedupe_window_sec"]:
                return True

        last_fuzzy = self._last_seen.get(f"{source_name}:fuzzy")
        if last_fuzzy and last_fuzzy[0] == fuzzy:
            if now - last_fuzzy[1] < 120:
                return True

        self._last_seen[f"{source_name}:exact"] = (exact, now)
        self._last_seen[f"{source_name}:fuzzy"] = (fuzzy, now)
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
