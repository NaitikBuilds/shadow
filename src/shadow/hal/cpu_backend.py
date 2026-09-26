import os

from .base import InferenceBackend
from .onnx_embedder import OnnxEmbedder

SYSTEM_PROMPT = (
    "You are SHADOW, a private, on-device life context agent. "
    "You run entirely on the user's laptop. You are calm, concise, and helpful. "
    "You never mention that you are an AI language model. "
    "When the user asks about their past activity, notes, or intentions, "
    "answer based on what you know. Keep answers short unless asked for detail."
)


class CpuBackend(InferenceBackend):
    def __init__(
        self,
        model_path: str,
        n_ctx: int = 4096,
        n_threads: int | None = None,
        n_gpu_layers: int = 0,
        embedder_model: str | None = None,
        embedder_tokenizer: str | None = None,
    ):
        from llama_cpp import Llama

        if n_threads is None:
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

        self.embedder: OnnxEmbedder | None = None
        if embedder_model and embedder_tokenizer:
            self.embedder = OnnxEmbedder(embedder_model, embedder_tokenizer)

    def generate(self, prompt: str, **kwargs) -> str:
        return "".join(self.generate_stream(prompt, **kwargs)).strip()

    def generate_stream(self, prompt: str, **kwargs):
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        stream = self.llm.create_chat_completion(
            messages=messages,
            max_tokens=kwargs.get("max_tokens", 256),
            temperature=kwargs.get("temperature", 0.7),
            top_p=kwargs.get("top_p", 0.9),
            repeat_penalty=kwargs.get("repeat_penalty", 1.1),
            stream=True,
        )
        for chunk in stream:
            delta = chunk["choices"][0]["delta"]
            if "content" in delta:
                yield delta["content"]

    def embed(self, text: str) -> list[float]:
        if self.embedder is None:
            raise RuntimeError(
                "Embedder not configured. Run scripts/download_embedder.py "
                "and set model.embedder_model / model.embedder_tokenizer in config.yaml."
            )
        return self.embedder.embed(text)

    @property
    def info(self) -> dict:
        return {
            "backend": "cpu",
            "model": getattr(self.llm, "model_path", "unknown"),
            "threads": self.n_threads,
            "embedder": "minilm-l6-v2-quantized" if self.embedder else "none",
        }