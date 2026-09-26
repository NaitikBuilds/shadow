import numpy as np

from .base import InferenceBackend


class CpuBackend(InferenceBackend):
    """CPU inference backend using llama-cpp-python."""

    def __init__(
        self,
        model_path: str,
        n_ctx: int = 4096,
        n_threads: int = 6,
        n_gpu_layers: int = 0,
    ):
        from llama_cpp import Llama  # imported lazily so tests don't need it

        self.llm = Llama(
            model_path=model_path,
            n_ctx=n_ctx,
            n_threads=n_threads,
            n_gpu_layers=n_gpu_layers,
            verbose=False,
        )

    def generate(self, prompt: str, **kwargs) -> str:
        max_tokens = kwargs.get("max_tokens", 512)
        temperature = kwargs.get("temperature", 0.7)
        out = self.llm(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            echo=False,
        )
        return out["choices"][0]["text"].strip()

    def embed(self, text: str) -> list[float]:
        # Placeholder — replaced with ONNX MiniLM in Phase 1.
        rng = np.random.default_rng(abs(hash(text)) % (2**32))
        return rng.random(384).astype(float).tolist()

    @property
    def info(self) -> dict:
        return {"backend": "cpu", "model": getattr(self.llm, "model_path", "unknown")}