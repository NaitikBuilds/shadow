"""CLI for managing SHADOW's local model files.

Usage:
    python scripts/manage_models.py list
    python scripts/manage_models.py download chat
    python scripts/manage_models.py download-all
    python scripts/manage_models.py download-all --include-optional
    python scripts/manage_models.py verify
"""

import argparse
import sys
from pathlib import Path

# Ensure src/ is importable when running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shadow.config import load_config  # noqa: E402
from shadow.memory import MemoryStore  # noqa: E402
from shadow.models import MODELS, ModelManager  # noqa: E402


def _make_manager() -> ModelManager:
    cfg = load_config()
    cache_dir = cfg.get("models", {}).get("cache_dir", "models")
    memory = MemoryStore(cfg["memory"]["db_path"], cfg["memory"]["vector_dim"])
    return ModelManager(cache_dir=cache_dir, memory=memory, progress=_progress)


def _progress(done: int, total: int) -> None:
    if total <= 0:
        return
    pct = done * 100 // total
    mb = done // (1024 * 1024)
    total_mb = total // (1024 * 1024)
    bar = "=" * (pct // 3) + " " * (33 - pct // 3)
    sys.stdout.write(f"\r  [{bar}] {pct:3d}%  {mb}/{total_mb} MB")
    sys.stdout.flush()
    if done >= total:
        sys.stdout.write("\n")


def cmd_list(mgr: ModelManager) -> int:
    status = mgr.status()
    print(f"{'ID':<22} {'ROLE':<10} {'STATUS':<12} {'SIZE':>10}  NAME")
    print("-" * 80)
    for mid, info in status.items():
        if not info["present"]:
            state = "missing"
        elif info["verified"]:
            state = "ok"
        else:
            state = "unverified"
        size_mb = info["size_bytes"] // (1024 * 1024)
        opt = " (optional)" if info["optional"] else ""
        print(
            f"{mid:<22} {info['role']:<10} {state:<12} "
            f"{size_mb:>7} MB  {info['name']}{opt}"
        )
    return 0


def cmd_download(mgr: ModelManager, model_id: str) -> int:
    if model_id not in MODELS:
        print(f"Unknown model: {model_id}")
        return 1
    print(f"Downloading {MODELS[model_id].name}...")
    result = mgr.ensure(model_id)
    verb = "cached" if result.from_cache else "downloaded"
    print(f"  {verb}: {result.path}")
    print(f"  sha256: {result.sha256}")
    return 0


def cmd_download_all(mgr: ModelManager, include_optional: bool) -> int:
    results = mgr.ensure_all(required_only=not include_optional)
    for r in results:
        verb = "cached" if r.from_cache else "downloaded"
        print(f"  {r.model_id:<20} {verb}")
    return 0


def cmd_verify(mgr: ModelManager) -> int:
    status = mgr.status()
    ok = True
    for mid, info in status.items():
        if not info["present"]:
            print(f"  {mid}: missing")
            if not info["optional"]:
                ok = False
        elif info["verified"]:
            print(f"  {mid}: ok")
        else:
            print(f"  {mid}: HASH MISMATCH")
            ok = False
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="SHADOW model manager")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="Show model status")

    p_dl = sub.add_parser("download", help="Download a specific model")
    p_dl.add_argument("model_id")

    p_dla = sub.add_parser("download-all", help="Download all models")
    p_dla.add_argument("--include-optional", action="store_true")

    sub.add_parser("verify", help="Verify all hashes")

    args = parser.parse_args()
    mgr = _make_manager()

    if args.cmd == "list":
        return cmd_list(mgr)
    if args.cmd == "download":
        return cmd_download(mgr, args.model_id)
    if args.cmd == "download-all":
        return cmd_download_all(mgr, args.include_optional)
    if args.cmd == "verify":
        return cmd_verify(mgr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
