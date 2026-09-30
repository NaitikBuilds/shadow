"""Download, verify, and manage SHADOW's local model files."""

import hashlib
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from .registry import MODELS, ModelSpec

# Bytes buffer required beyond the model size itself.
DISK_HEADROOM_BYTES = 500 * 1024 * 1024

# Download retry schedule (seconds).
RETRY_DELAYS = [5, 30, 120]

# Read size for hashing and copy operations.
CHUNK_SIZE = 1024 * 1024  # 1 MB


@dataclass
class DownloadResult:
    model_id: str
    path: Path
    sha256: str
    size_bytes: int
    from_cache: bool


ProgressFn = Callable[[int, int], None]  # (bytes_done, total_bytes)


class ModelManager:
    """Manages local model files in a cache directory.

    Responsibilities:
      - Download with resume on interrupted transfers
      - SHA256 verify (registry hash or first-run computed sidecar)
      - Store per-model hash in schema_meta for version tracking
      - Check disk space before download
      - Retry failed downloads with exponential backoff
    """

    def __init__(
        self,
        cache_dir: str | Path,
        memory=None,  # optional MemoryStore for version tracking
        progress: ProgressFn | None = None,
    ):
        self.cache_dir = Path(cache_dir).expanduser().resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.memory = memory
        self.progress = progress

    # ---------- public API ----------

    def path_for(self, model_id: str) -> Path:
        spec = MODELS[model_id]
        return self.cache_dir / spec.filename

    def is_present(self, model_id: str) -> bool:
        path = self.path_for(model_id)
        return path.exists() and path.stat().st_size > 0

    def verify(self, model_id: str) -> bool:
        """Return True if the file is present and its SHA256 matches."""
        spec = MODELS[model_id]
        path = self.path_for(model_id)
        if not path.exists():
            return False
        expected = self._expected_hash(spec, path)
        if expected is None:
            return True  # can't verify without an expected value
        return self._hash_file(path) == expected

    def ensure(self, model_id: str) -> DownloadResult:
        """Ensure the model is present and verified. Download if needed."""
        spec = MODELS[model_id]
        path = self.path_for(model_id)

        if path.exists() and self.verify(model_id):
            return DownloadResult(
                model_id=model_id,
                path=path,
                sha256=self._expected_hash(spec, path) or "",
                size_bytes=path.stat().st_size,
                from_cache=True,
            )

        return self._download_with_retry(spec)

    def ensure_all(self, required_only: bool = True) -> list[DownloadResult]:
        """Ensure all (or just required) models are present."""
        results = []
        for spec in MODELS.values():
            if required_only and spec.optional:
                continue
            results.append(self.ensure(spec.id))
        return results

    def status(self) -> dict[str, dict]:
        """Return per-model status for UI display."""
        out: dict[str, dict] = {}
        for mid, spec in MODELS.items():
            path = self.path_for(mid)
            present = path.exists()
            verified = self.verify(mid) if present else False
            out[mid] = {
                "name": spec.name,
                "role": spec.role,
                "optional": spec.optional,
                "present": present,
                "verified": verified,
                "size_bytes": path.stat().st_size if present else 0,
                "path": str(path),
            }
        return out

    # ---------- download ----------

    def _download_with_retry(self, spec: ModelSpec) -> DownloadResult:
        last_exc: Exception | None = None
        for attempt, delay in enumerate([0] + RETRY_DELAYS):
            if delay:
                time.sleep(delay)
            try:
                return self._download(spec)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                continue
        raise RuntimeError(
            f"Download failed after {len(RETRY_DELAYS) + 1} attempts: {last_exc}"
        ) from last_exc

    def _download(self, spec: ModelSpec) -> DownloadResult:
        import requests

        target = self.path_for(spec)
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".partial")

        # Disk space check
        free = shutil.disk_usage(target.parent).free
        needed = (spec.size_bytes or 0) + DISK_HEADROOM_BYTES
        if spec.size_bytes and free < needed:
            raise RuntimeError(
                f"Not enough disk space for {spec.name}. "
                f"Need ~{needed // (1024**3)} GB, have {free // (1024**3)} GB."
            )

        # Resume support
        resume_at = partial.stat().st_size if partial.exists() else 0
        headers = {}
        if resume_at:
            headers["Range"] = f"bytes={resume_at}-"

        urls = [spec.url] + list(spec.mirrors)
        last_exc: Exception | None = None
        for url in urls:
            try:
                with requests.get(url, stream=True, timeout=60, headers=headers) as r:
                    if resume_at and r.status_code == 206:
                        mode = "ab"
                    elif r.status_code == 200:
                        mode = "wb"
                        resume_at = 0
                    else:
                        r.raise_for_status()
                        continue

                    total = int(r.headers.get("Content-Length", 0)) + resume_at
                    done = resume_at
                    with open(partial, mode) as f:
                        for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                            if not chunk:
                                continue
                            f.write(chunk)
                            done += len(chunk)
                            if self.progress:
                                self.progress(done, total)

                # Atomic rename on success
                os.replace(partial, target)
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                continue
        else:
            raise RuntimeError(f"All mirrors failed: {last_exc}")

        # Compute and store hash
        sha = self._hash_file(target)
        self._write_sidecar(target, sha)
        self._record_version(spec.id, sha)

        return DownloadResult(
            model_id=spec.id,
            path=target,
            sha256=sha,
            size_bytes=target.stat().st_size,
            from_cache=False,
        )

    # ---------- hashing ----------

    @staticmethod
    def _hash_file(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                block = f.read(CHUNK_SIZE)
                if not block:
                    break
                h.update(block)
        return h.hexdigest()

    @staticmethod
    def _sidecar_path(path: Path) -> Path:
        return path.with_suffix(path.suffix + ".sha256")

    def _expected_hash(self, spec: ModelSpec, path: Path) -> str | None:
        if spec.sha256:
            return spec.sha256
        sidecar = self._sidecar_path(path)
        if sidecar.exists():
            return sidecar.read_text(encoding="utf-8").strip() or None
        return None

    def _write_sidecar(self, path: Path, sha: str) -> None:
        self._sidecar_path(path).write_text(sha, encoding="utf-8")

    # ---------- version tracking ----------

    def _record_version(self, model_id: str, sha: str) -> None:
        if self.memory is None:
            return
        try:
            cur = self.memory.conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO schema_meta (key, value) VALUES (?, ?)",
                (f"model.{model_id}.sha256", sha),
            )
            self.memory.conn.commit()
        except Exception:  # noqa: BLE001
            pass

    def get_recorded_version(self, model_id: str) -> str | None:
        if self.memory is None:
            return None
        cur = self.memory.conn.cursor()
        cur.execute(
            "SELECT value FROM schema_meta WHERE key = ?",
            (f"model.{model_id}.sha256",),
        )
        row = cur.fetchone()
        return row[0] if row else None
