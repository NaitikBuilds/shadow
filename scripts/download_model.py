"""Download a small GGUF model for local inference."""

from pathlib import Path

import requests

MODEL_URL = (
    "https://huggingface.co/LiquidAI/LFM2-350M-GGUF/" "resolve/main/LFM2-350M-Q4_0.gguf"
)
DEST = Path("models/LFM2-350M-Q4_0.gguf")


def download() -> None:
    DEST.parent.mkdir(parents=True, exist_ok=True)
    if DEST.exists():
        print(f"Model already exists at {DEST}")
        return
    print(f"Downloading {MODEL_URL} …")
    with requests.get(MODEL_URL, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", 0))
        done = 0
        with open(DEST, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                f.write(chunk)
                done += len(chunk)
                if total:
                    pct = done * 100 // total
                    mb = done // (1024 * 1024)
                    total_mb = total // (1024 * 1024)
                    print(f"\r  {pct:3d}%  {mb}/{total_mb} MB", end="", flush=True)
    print()
    print(f"Saved to {DEST}")


if __name__ == "__main__":
    download()
