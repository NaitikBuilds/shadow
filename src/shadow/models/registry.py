"""Declarative registry of models SHADOW uses.

Each entry describes a single downloadable file. Multi-file models (like
the embedder, which needs both an ONNX file and a tokenizer) are split
into separate entries so each can be verified independently.

Hashes are optional. When absent, the manager computes and stores one
on first download. This lets us ship without hardcoding Hugging Face
checksums while still detecting corruption after the first run.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelSpec:
    id: str
    name: str
    filename: str  # relative to cache_dir
    url: str
    mirrors: list[str] = field(default_factory=list)
    sha256: str | None = None
    size_bytes: int = 0
    role: str = ""  # "chat" | "embedder" | "vision" | "planner" | "asr"
    optional: bool = False  # if True, skipped by download_all(required_only=True)


MODELS: dict[str, ModelSpec] = {
    "chat": ModelSpec(
        id="chat",
        name="Qwen2.5-1.5B-Instruct (Q4_K_M)",
        filename="qwen2.5-1.5b-instruct-q4_k_m.gguf",
        url=(
            "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/"
            "resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"
        ),
        size_bytes=1_117_320_736,
        role="chat",
        optional=False,
    ),
    "embedder_model": ModelSpec(
        id="embedder_model",
        name="all-MiniLM-L6-v2 ONNX (quantized)",
        filename="minilm/model.onnx",
        url=(
            "https://huggingface.co/Xenova/all-MiniLM-L6-v2/"
            "resolve/main/onnx/model_quantized.onnx"
        ),
        size_bytes=22_974_462,
        role="embedder",
        optional=False,
    ),
    "embedder_tokenizer": ModelSpec(
        id="embedder_tokenizer",
        name="all-MiniLM-L6-v2 tokenizer",
        filename="minilm/tokenizer.json",
        url=(
            "https://huggingface.co/Xenova/all-MiniLM-L6-v2/"
            "resolve/main/tokenizer.json"
        ),
        size_bytes=711_661,
        role="embedder",
        optional=False,
    ),
    "vision": ModelSpec(
        id="vision",
        name="Moondream2 (Q4, GGUF)",
        filename="moondream2/moondream2-q4.gguf",
        url=(
            "https://huggingface.co/vikhyatk/moondream2/"
            "resolve/main/moondream2-text-model-f16.gguf"
        ),
        size_bytes=1_800_000_000,
        role="vision",
        optional=True,
    ),
    "planner": ModelSpec(
        id="planner",
        name="Qwen2.5-7B-Instruct (Q4_K_M)",
        filename="qwen2.5-7b-instruct-q4_k_m.gguf",
        url=(
            "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/"
            "resolve/main/qwen2.5-7b-instruct-q4_k_m.gguf"
        ),
        size_bytes=4_683_072_192,
        role="planner",
        optional=True,
    ),
    "asr": ModelSpec(
        id="asr",
        name="Whisper tiny.en (ggml)",
        filename="whisper/ggml-tiny.en.bin",
        url=(
            "https://huggingface.co/ggerganov/whisper.cpp/"
            "resolve/main/ggml-tiny.en.bin"
        ),
        size_bytes=77_691_713,
        role="asr",
        optional=True,
    ),
}
