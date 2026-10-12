"""Moondream2 CPU vision backend using llama.cpp.

Loads Moondream2 via llama-cpp-python with the mmproj vision encoder.
Implements the inference backend's optional understand_image() method.

Design notes:
  - Lazy load: the model only loads on the first vision call.
  - Auto unload: released after UNLOAD_AFTER_SEC of idle time.
  - Reuses llama-cpp-python, already a project dependency.
  - Task prompts are fixed templates except for "query" which uses
    the caller's prompt verbatim.
"""

import base64
import threading
import time
from pathlib import Path

from .base import (
    TASK_CAPTION,
    TASK_DETAILED_CAPTION,
    TASK_OCR,
    TASK_QUERY,
    InferenceBackend,
)

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
        self._lock = threading.RLock()
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
        llm = self._ensure_loaded()
        max_tokens = kwargs.get("max_tokens", 256)
        temperature = kwargs.get("temperature", 0.3)
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
        # (ScreenVisionSource) treats empty as "no result" and moves on.
        try:
            llm = self._ensure_loaded()
        except Exception:
            return ""

        try:
            data_uri = self._to_data_uri(image_bytes)
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
            self._last_used_at = time.monotonic()
            text = (
                response.get("choices", [{}])[0].get("message", {}).get("content", "")
            )
            return (text or "").strip()
        except Exception:
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
        self._unload_stop.set()
        if self._unload_thread is not None:
            self._unload_thread.join(timeout=2)
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

    def _ensure_loaded(self):
        with self._lock:
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

            self._llm = Llama(
                model_path=str(text_path),
                clip_model_path=str(mmproj_path),
                n_ctx=self.n_ctx,
                n_threads=self.n_threads,
                n_gpu_layers=self.n_gpu_layers,
                verbose=False,
            )
            self._last_used_at = time.monotonic()
            self._start_unload_watchdog()
            return self._llm

    def _release_model(self) -> None:
        with self._lock:
            if self._llm is None:
                return
            try:
                self._llm.close()
            except Exception:
                pass
            self._llm = None

    def _start_unload_watchdog(self) -> None:
        if self._unload_thread is not None and self._unload_thread.is_alive():
            return
        self._unload_stop.clear()

        def _watch():
            while not self._unload_stop.is_set():
                if self._unload_stop.wait(30):
                    break
                with self._lock:
                    if self._llm is None:
                        return
                    idle = time.monotonic() - self._last_used_at
                    if idle >= UNLOAD_AFTER_SEC:
                        try:
                            self._llm.close()
                        except Exception:
                            pass
                        self._llm = None
                        return

        self._unload_thread = threading.Thread(
            target=_watch, daemon=True, name="moondream-unload"
        )
        self._unload_thread.start()
