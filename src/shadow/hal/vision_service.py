"""VisionService — lazy-loaded wrapper for a vision backend.

Provides a single entry point for image analysis without forcing
the caller to construct a vision backend directly. Handles:

  - Lazy model load on first analyze() call
  - Thread-safe access
  - Automatic reuse of the loaded model
  - Graceful failure when the model files are missing
  - Optional unload via the backend's own idle timer

Callers pass image bytes and a task; the service handles everything else.
"""

import threading

from .base import TASK_CAPTION, TASK_DETAILED_CAPTION, TASK_OCR, TASK_QUERY


class VisionService:
    """Lazy-loading wrapper around a vision-capable InferenceBackend."""

    def __init__(self, backend_factory, enabled: bool = True):
        """backend_factory is a callable that returns a vision backend.

        The factory runs at most once, on the first analyze() call.
        """
        self._factory = backend_factory
        self._enabled = enabled
        self._backend = None
        self._lock = threading.RLock()
        self._load_failed = False

    # ---------- public API ----------

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, value: bool) -> None:
        self._enabled = bool(value)

    def is_available(self) -> bool:
        """True if the service can be used (enabled and not load-failed)."""
        if not self._enabled:
            return False
        return not self._load_failed

    def is_loaded(self) -> bool:
        with self._lock:
            return self._backend is not None

    def analyze(
        self,
        image_bytes: bytes,
        task: str = TASK_CAPTION,
        prompt: str = "",
        **kwargs,
    ) -> str:
        """Analyze an image. Returns text or empty string on failure."""
        if not self._enabled or self._load_failed:
            return ""
        if not image_bytes:
            return ""

        backend = self._ensure_backend()
        if backend is None:
            return ""

        try:
            return backend.understand_image(image_bytes, task=task, prompt=prompt, **kwargs)
        except Exception:
            return ""

    # ---------- convenience ----------

    def caption(self, image_bytes: bytes) -> str:
        return self.analyze(image_bytes, task=TASK_CAPTION)

    def detailed_caption(self, image_bytes: bytes) -> str:
        return self.analyze(image_bytes, task=TASK_DETAILED_CAPTION)

    def ocr(self, image_bytes: bytes) -> str:
        return self.analyze(image_bytes, task=TASK_OCR)

    def query(self, image_bytes: bytes, question: str) -> str:
        return self.analyze(image_bytes, task=TASK_QUERY, prompt=question)

    def close(self) -> None:
        with self._lock:
            if self._backend is not None:
                try:
                    self._backend.close()
                except Exception:
                    pass
                self._backend = None

    # ---------- internals ----------

    def _ensure_backend(self):
        with self._lock:
            if self._backend is not None:
                return self._backend
            if self._load_failed:
                return None
            try:
                self._backend = self._factory()
            except Exception:
                self._load_failed = True
                return None
            return self._backend
