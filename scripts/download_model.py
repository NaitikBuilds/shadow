"""Download a small GGUF model for local inference."""
from pathlib import Path

import requests

MODEL_URL = (
    "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/"
    "qwen2.5-1.5b-instruct-q4_k_m.gguf"
)
DEST = Path("models/qwen2.5-1.5b-instruct-q4_k_m.gguf")


def download() -> None:
    DEST.parent.mkdir(parents=True, exist_ok=True)
    if DEST.exists():
        print(f"Model already exists at {DEST}")
        return
    print(f"Downloading {MODEL_URL} …")
    with requests.get(MODEL_URL, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(DEST, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    print(f"Saved to {DEST}")


if __name__ == "__main__":
    download()