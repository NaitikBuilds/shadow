"""Moondream2 CPU vision backend using llama.cpp.

Loads Moondream2 via llama-cpp-python with the mmproj vision encoder and the
package's MoondreamChatHandler. Implements the inference backend's optional
understand_image() method.

Design notes:
  - Lazy load: the model only loads on the first vision call.
  - Auto unload: released after UNLOAD_AFTER_SEC of idle time.
  - Reuses llama-cpp-python, already a project dependency.
  - Task prompts are fixed templates except for "query" which uses
    the caller's prompt verbatim.
  - The chat handler owns native CLIP/image-embed state that llama-cpp-python
    does not free on its own, so the backend releases it together with Llama.
"""

import base64
import logging
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from .base import (
    TASK_CAPTION,
    TASK_DETAILED_CAPTION,
    TASK_OCR,
    TASK_QUERY,
    InferenceBackend,
)

logger = logging.getLogger(__name__)

UNLOAD_AFTER_SEC = 300  # 5 minutes

TASK_PROMPTS = {
    TASK_CAPTION: "Describe this image briefly in one sentence.",
    TASK_DETAILED_CAPTION: (
        "Describe this image in detail. Cover the main subjects, "
        "the setting, and any visible text."
    ),
    TASK_OCR: (
        "Extract all visible text from this image. "
        "Return only the text, no commentary."
    ),
    TASK_QUERY: "",  # uses caller's prompt
}


class Moondream2Backend(InferenceBackend):
    """Vision-language backend for Moondream2 via llama.cpp."""

    def __init__(
        self,
        text_model_path: str,
        mmproj_path: str,
        n_ctx: int = 2048,
        n_threads: int | None = None,
        n_gpu_layers: int = 0,
    ):
        self.text_model_path = text_model_path
        self.mmproj_path = mmproj_path
        self.n_ctx = n_ctx
        self.n_threads = n_threads
        self.n_gpu_layers = n_gpu_layers

        self._llm = None
        self._chat_handler = None
        # Guards model/handler state. Generations hold a model session
        # (counted in _in_flight) for their whole duration so unloading can
        # never free native state underneath a running inference.
        self._lock = threading.RLock()
        self._inference_done = threading.Condition(self._lock)
        self._in_flight = 0
        self._closed = False
        self._last_used_at = 0.0
        self._unload_thread: threading.Thread | None = None
        self._unload_stop = threading.Event()

    # ---------- capability ----------

    def supports_vision(self) -> bool:
        return True

    # ---------- text methods (delegated to vision model) ----------

    def generate(self, prompt: str, **kwargs) -> str:
        return "".join(self.generate_stream(prompt, **kwargs)).strip()

    def generate_stream(self, prompt: str, **kwargs):
        """Text-only generation on Moondream. Rarely used; the chat
        role is handled by CpuBackend/CloudBackend."""
        max_tokens = kwargs.get("max_tokens", 256)
        temperature = kwargs.get("temperature", 0.3)
        # The session stays open for the whole stream, so the model cannot
        # be unloaded (and the handler's CLIP context freed) mid-generation.
        # If the caller abandons the generator, closing or collecting it
        # exits the context and ends the session.
        with self._model_session() as llm:
            stream = llm.create_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True,
            )
            for chunk in stream:
                delta = chunk["choices"][0]["delta"]
                if "content" in delta:
                    yield delta["content"]

    def embed(self, text: str) -> list[float]:
        raise NotImplementedError(
            "Moondream2Backend does not embed. Use the ONNX embedder."
        )

    # ---------- vision ----------

    def understand_image(
        self,
        image_bytes: bytes,
        task: str = TASK_CAPTION,
        prompt: str = "",
    ) -> str:
        if not image_bytes:
            return ""

        question = self._resolve_prompt(task, prompt)
        if not question:
            return ""

        # Load can fail if the model files are missing. The caller
        # (ScreenVisionSource) treats empty as "no result" and moves on, so
        # the original error is logged rather than raised.
        try:
            data_uri = self._to_data_uri(image_bytes)
            with self._model_session() as llm:
                response = llm.create_chat_completion(
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {"url": data_uri},
                                },
                                {"type": "text", "text": question},
                            ],
                        }
                    ],
                    max_tokens=256,
                    temperature=0.2,
                )
            text = (
                response.get("choices", [{}])[0].get("message", {}).get("content", "")
            )
            return (text or "").strip()
        except Exception:
            logger.debug("Moondream2 vision call failed", exc_info=True)
            return ""

    # ---------- lifecycle ----------

    @property
    def info(self) -> dict:
        return {
            "backend": "moondream2",
            "text_model": self.text_model_path,
            "mmproj": self.mmproj_path,
            "loaded": self._llm is not None,
        }

    def close(self) -> None:
        with self._lock:
            self._closed = True
        self._unload_stop.set()
        thread = self._unload_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)
        self._release_model()

    # ---------- internals ----------

    @staticmethod
    def _resolve_prompt(task: str, prompt: str) -> str:
        if task == TASK_QUERY:
            return prompt.strip()
        return TASK_PROMPTS.get(task, TASK_PROMPTS[TASK_CAPTION])

    @staticmethod
    def _to_data_uri(image_bytes: bytes) -> str:
        # Sniff PNG vs JPEG by magic bytes; default to JPEG.
        if image_bytes.startswith(b"\x89PNG"):
            mime = "image/png"
        elif image_bytes.startswith(b"\xff\xd8"):
            mime = "image/jpeg"
        else:
            mime = "image/png"
        b64 = base64.b64encode(image_bytes).decode("ascii")
        return f"data:{mime};base64,{b64}"

    @contextmanager
    def _model_session(self):
        """Yield the loaded model and hold it for the caller's duration.

        Unloading waits for in-flight sessions, so native state cannot be
        freed while a session is using it.
        """
        with self._lock:
            llm = self._ensure_loaded_locked()
            self._in_flight += 1
            self._last_used_at = time.monotonic()
        try:
            yield llm
        finally:
            with self._lock:
                self._in_flight -= 1
                self._last_used_at = time.monotonic()
                if self._in_flight == 0:
                    self._inference_done.notify_all()

    def _ensure_loaded(self):
        with self._lock:
            return self._ensure_loaded_locked()

    def _ensure_loaded_locked(self):
        if self._closed:
            raise RuntimeError("Moondream2Backend is closed")
        if self._llm is not None:
            self._last_used_at = time.monotonic()
            return self._llm

        text_path = Path(self.text_model_path)
        mmproj_path = Path(self.mmproj_path)
        if not text_path.exists():
            raise FileNotFoundError(f"Moondream2 text model missing: {text_path}")
        if not mmproj_path.exists():
            raise FileNotFoundError(f"Moondream2 mmproj missing: {mmproj_path}")

        from llama_cpp import Llama
        from llama_cpp.llama_chat_format import MoondreamChatHandler

        # The handler loads the vision (CLIP) encoder and owns its native
        # buffers. It must be handed to Llama explicitly: the default chat
        # format (llama-2) has no image support, and its registry does not
        # register "moondream".
        handler = None
        try:
            handler = MoondreamChatHandler(
                clip_model_path=str(mmproj_path),
                verbose=False,
            )
            llm = Llama(
                model_path=str(text_path),
                clip_model_path=str(mmproj_path),
                chat_handler=handler,
                n_ctx=self.n_ctx,
                n_threads=self.n_threads,
                n_gpu_layers=self.n_gpu_layers,
                verbose=False,
            )
        except BaseException:
            # Llama construction failed after the handler loaded the CLIP
            # encoder; free it here so nothing leaks, then surface the error.
            if handler is not None:
                self._release_chat_handler(handler)
            raise

        self._llm = llm
        self._chat_handler = handler
        self._last_used_at = time.monotonic()
        self._start_unload_watchdog()
        return llm

    @staticmethod
    def _release_chat_handler(handler) -> None:
        """Free a chat handler's native CLIP context and cached image embed.

        Older llama-cpp-python handlers keep these in an ``ExitStack`` and
        expose no close()/__del__, so the owner must close it. ExitStack
        close() is idempotent, so a redundant call cannot double-free.
        Newer mtmd-based handlers register their native context on the Llama
        instance's teardown stack instead, so ``llm.close()`` already freed it.
        """
        try:
            close = getattr(handler, "close", None)
            if callable(close):
                close()
                return
            exit_stack = getattr(handler, "_exit_stack", None)
            if exit_stack is not None:
                exit_stack.close()
                return
            if getattr(handler, "mtmd_ctx", None) is None and hasattr(
                handler, "mtmd_ctx"
            ):
                # Owned by the Llama teardown stack; nothing left to free here.
                return
            logger.warning(
                "Moondream chat handler exposes no cleanup hooks: %r", handler
            )
        except Exception:
            logger.exception("Failed to release Moondream chat handler resources")

    def _close_model_locked(self) -> None:
        """Release Llama and the chat handler exactly once.

        The caller must hold self._lock and guarantee that no inference is
        in flight. References are dropped before the native teardown so a
        failure part-way cannot leave a half-closed model reachable.
        """
        llm, handler = self._llm, self._chat_handler
        self._llm = None
        self._chat_handler = None

        try:
            if llm is not None:
                try:
                    llm.close()
                except Exception:
                    logger.exception("Failed to close Moondream Llama instance")
        finally:
            # The handler's buffer(s) are independent of the Llama context,
            # so they are released whether or not llm.close() succeeded.
            if handler is not None:
                self._release_chat_handler(handler)

    def _release_model(self) -> None:
        """Release native state, waiting for in-flight generations."""
        with self._lock:
            while self._in_flight > 0:
                self._inference_done.wait()
            self._close_model_locked()

    def _unload_if_idle(self) -> bool:
        """Unload the model when it has been idle. Return True if unloaded.

        Returns False when a generation is running or the model was used
        recently, so the watchdog retries on its next tick.
        """
        with self._lock:
            if self._llm is None:
                return True
            if self._in_flight > 0:
                return False
            if time.monotonic() - self._last_used_at < UNLOAD_AFTER_SEC:
                return False
            self._close_model_locked()
            return True

    def _start_unload_watchdog(self) -> None:
        if self._unload_thread is not None and self._unload_thread.is_alive():
            return
        self._unload_stop.clear()

        def _watch():
            while not self._unload_stop.wait(30):
                if self._unload_if_idle():
                    return

        self._unload_thread = threading.Thread(
            target=_watch, daemon=True, name="moondream-unload"
        )
        self._unload_thread.start()
