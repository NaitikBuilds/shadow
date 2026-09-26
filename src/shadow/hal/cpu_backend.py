import os

import numpy as np

from .base import InferenceBackend

SYSTEM_PROMPT = (
    "You are SHADOW, a private, on-device life context agent. "
    "You run entirely on the user's laptop. You are calm, concise, and helpful. "
    "You never mention that you are an AI language model. "
    "When the user asks about their past activity, notes, or intentions, "
    "answer based on what you know. Keep answers short unless asked for detail."
)


class CpuBackend(InferenceBackend):
    """CPU inference backend using llama-cpp-python."""

    def __init__(
        self,
        model_path: str,
        n_ctx: int = 4096,
        n_threads: int | None = None,
        n_gpu_layers: int = 0,
    ):
        from llama_cpp import Llama  # lazy import

        if n_threads is None:
            # rule of thumb: use (logical cores / 2) - 1 for llama.cpp
            logical = os.cpu_count() or 4
            n_threads = max(2, (logical // 2) - 1)

        self.llm = Llama(
            model_path=model_path,
            n_ctx=n_ctx,
            n_threads=n_threads,
            n_gpu_layers=n_gpu_layers,
            verbose=False,
        )
        self.n_threads = n_threads

    def generate(self, prompt: str, **kwargs) -> str:
        """Non-streaming generate (kept for tests and internal calls)."""
        chunks = list(self.generate_stream(prompt, **kwargs))
        return "".join(chunks).strip()

    def generate_stream(self, prompt: str, **kwargs):
        """Yield response chunks as they are produced."""
        max_tokens = kwargs.get("max_tokens", 256)
        temperature = kwargs.get("temperature", 0.7)
        top_p = kwargs.get("top_p", 0.9)
        repeat_penalty = kwargs.get("repeat_penalty", 1.1)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        stream = self.llm.create_chat_completion(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            repeat_penalty=repeat_penalty,
            stream=True,
        )

        for chunk in stream:
            delta = chunk["choices"][0]["delta"]
            if "content" in delta:
                yield delta["content"]

    def embed(self, text: str) -> list[float]:
        # Placeholder — replaced with ONNX MiniLM in Phase 1.
        rng = np.random.default_rng(abs(hash(text)) % (2**32))
        return rng.random(384).astype(float).tolist()

    @property
    def info(self) -> dict:
        return {
            "backend": "cpu",
            "model": getattr(self.llm, "model_path", "unknown"),
            "threads": self.n_threads,
        }