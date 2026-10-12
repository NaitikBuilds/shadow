"""Inference backend interface — hardware and provider agnostic."""

from abc import ABC, abstractmethod

# Vision task identifiers. Callers pass one of these to understand_image().
TASK_CAPTION = "caption"
TASK_DETAILED_CAPTION = "detailed_caption"
TASK_OCR = "ocr"
TASK_QUERY = "query"

VALID_TASKS = frozenset(
    {
        TASK_CAPTION,
        TASK_DETAILED_CAPTION,
        TASK_OCR,
        TASK_QUERY,
    }
)


class InferenceBackend(ABC):
    """Hardware-agnostic inference interface.

    Every backend (CPU, Snapdragon NPU, cloud) implements the text
    methods. Vision is optional — the default raises NotImplementedError
    so backends that don't do vision stay valid.

    Implementations:

      - CpuBackend: local chat via llama.cpp. No vision.
      - CloudBackend: remote chat via OpenAI-compatible endpoint. No vision.
      - ProviderPool: multi-provider failover. Delegates vision to local fallback.
      - HybridBackend: cloud-or-local routing. Delegates vision to local.
      - Florence2Backend: local vision via ONNX Runtime. (Commit 2)
      - Moondream2Backend: local vision via llama.cpp + mmproj. (Commit 3)
    """

    # ---------- text generation ----------

    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str: ...

    @abstractmethod
    def generate_stream(self, prompt: str, **kwargs): ...

    # ---------- embeddings ----------

    @abstractmethod
    def embed(self, text: str) -> list[float]: ...

    # ---------- vision (optional) ----------

    def understand_image(
        self,
        image_bytes: bytes,
        task: str = TASK_CAPTION,
        prompt: str = "",
    ) -> str:
        """Analyze an image and return text.

        Args:
            image_bytes: PNG or JPEG-encoded image data.
            task: one of VALID_TASKS. Default is a short caption.
            prompt: optional question when task is "query".

        Returns:
            Text result. Empty string if nothing useful.

        Raises:
            NotImplementedError: if this backend has no vision support.
            ValueError: if task is invalid.
        """
        if task not in VALID_TASKS:
            raise ValueError(
                f"unknown vision task: {task!r}. " f"Valid tasks: {sorted(VALID_TASKS)}"
            )
        raise NotImplementedError(
            f"{type(self).__name__} does not support vision. "
            "Use a vision-capable backend."
        )

    def supports_vision(self) -> bool:
        """Return True if this backend can analyze images."""
        return False

    # ---------- introspection ----------

    @property
    @abstractmethod
    def info(self) -> dict: ...
