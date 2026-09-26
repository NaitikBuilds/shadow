"""Download the ONNX MiniLM embedder + tokenizer."""
from pathlib import Path
import requests

BASE = "https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main"
FILES = {
    "onnx/model_quantized.onnx": "models/minilm/model.onnx",
    "tokenizer.json": "models/minilm/tokenizer.json",
}


def download():
    for url_path, dest in FILES.items():
        url = f"{BASE}/{url_path}"
        out = Path(dest)
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            print(f"✓ {out} already exists")
            continue
        print(f"↓ {url}")
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(out, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        print(f"  saved {out}")


if __name__ == "__main__":
    download()