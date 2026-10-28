"""Phase 4 privacy test harness (C02).

Reusable spies, fakes, and scanners used by every Phase 4 privacy test.

Contract:
  - A spy that observes a call does NOT raise by default (observations only).
  - Assertion is done via `spy.assert_*` helpers, in the test.
  - Nothing here touches the real network or the real model directory.

Usage in a Phase 4 feature test:

    def test_something(phase4_spies):
        phase4_spies.fake_vlm.set_response("a chart")
        # ... drive the feature ...
        phase4_spies.cloud_spy.assert_not_called()
        phase4_spies.vlm_spy.assert_called_times(1)
        phase4_spies.db_scanner.assert_no_image_blobs(conn)
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


# ---------------------------------------------------------------------------
# Fake clock — deterministic time for scheduler / retention tests
# ---------------------------------------------------------------------------
class FakeClock:
    def __init__(self, start: float | None = None) -> None:
        self._now = start if start is not None else 1_700_000_000.0
        self._lock = threading.Lock()

    def now(self) -> float:
        with self._lock:
            return self._now

    def now_utc(self) -> datetime:
        return datetime.fromtimestamp(self.now(), tz=UTC)

    def advance(self, seconds: float) -> float:
        with self._lock:
            self._now += float(seconds)
            return self._now

    def set(self, epoch: float) -> None:
        with self._lock:
            self._now = float(epoch)

    def patch(self, monkeypatch, module) -> None:
        """Patch `time.time` and `datetime.now` inside a target module."""
        monkeypatch.setattr(module, "time", self, raising=False)  # type: ignore[attr-defined]
        monkeypatch.setattr(module.time, "time", self.now, raising=False)


# ---------------------------------------------------------------------------
# Fake VLM — deterministic captions, no model load
# ---------------------------------------------------------------------------
class FakeVLM:
    def __init__(self, default_caption: str = "fake caption") -> None:
        self.default_caption = default_caption
        self.responses: list[str] = []
        self.calls: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def set_response(self, *captions: str) -> None:
        with self._lock:
            self.responses = list(captions)

    def caption(self, image: Any, **kwargs: Any) -> str:
        with self._lock:
            self.calls.append({"image_len": len(image) if image else 0, **kwargs})
            if self.responses:
                return self.responses.pop(0)
            return self.default_caption

    # Convenience aliases for likely feature interfaces
    def describe(self, image: Any, **kwargs: Any) -> str:
        return self.caption(image, **kwargs)

    def load(self) -> None: ...
    def unload(self) -> None: ...


# ---------------------------------------------------------------------------
# Spy — general call observer
# ---------------------------------------------------------------------------
class Spy:
    """Records every call. Never raises. Asserts in tests via assert_* helpers."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[tuple[tuple, dict]] = []
        self._lock = threading.Lock()

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        with self._lock:
            self.calls.append((args, kwargs))

    def reset(self) -> None:
        with self._lock:
            self.calls.clear()

    def called(self) -> bool:
        with self._lock:
            return bool(self.calls)

    def called_times(self) -> int:
        with self._lock:
            return len(self.calls)

    def assert_not_called(self) -> None:
        n = self.called_times()
        assert n == 0, f"{self.name} called {n} times, expected 0; calls={self.calls}"

    def assert_called_times(self, expected: int) -> None:
        n = self.called_times()
        assert n == expected, f"{self.name} called {n} times, expected {expected}"

    def assert_called_with(self, *args: Any) -> None:
        assert any(
            a == args for a, _ in self.calls
        ), f"{self.name} never called with {args!r}"


# ---------------------------------------------------------------------------
# CloudBackend spy — fails if any call happens during a privacy test
# ---------------------------------------------------------------------------
class CloudBackendSpy:
    """Monkeypatch-target that records every attribute access, then raises if
    used. Tests call `spy.assert_not_called()` or use `with spy.scoped():`."""

    def __init__(self) -> None:
        self.understand_image = Spy("CloudBackend.understand_image")
        self.chat = Spy("CloudBackend.chat")
        self.understand = Spy("CloudBackend.understand")
        self.complete = Spy("CloudBackend.complete")
        self._inner_spies = [
            self.understand_image,
            self.chat,
            self.understand,
            self.complete,
        ]

    def assert_not_called(self) -> None:
        for s in self._inner_spies:
            s.assert_not_called()

    def reset(self) -> None:
        for s in self._inner_spies:
            s.reset()

    def __getattr__(self, name: str):
        # Any *other* attribute on the CloudBackend gets recorded too.
        spy = Spy(f"CloudBackend.{name}")
        setattr(self, name, spy)
        self._inner_spies.append(spy)
        return spy


# ---------------------------------------------------------------------------
# VisionRouter spy — distinguishes local vs cloud routing
# ---------------------------------------------------------------------------
@dataclass
class VisionRouterSpy:
    local_calls: Spy = field(default_factory=lambda: Spy("vision.local"))
    cloud_calls: Spy = field(default_factory=lambda: Spy("vision.cloud"))

    def route(self, backend: str = "local", *args: Any, **kwargs: Any) -> None:
        (self.local_calls if backend == "local" else self.cloud_calls)(*args, **kwargs)

    def assert_local_only(self) -> None:
        self.local_calls.assert_not_called() if False else None
        self.cloud_calls.assert_not_called()


# ---------------------------------------------------------------------------
# Network blocker — any socket/requests/http call inside the test is a failure
# ---------------------------------------------------------------------------
class NetworkBlocker:
    def __init__(self) -> None:
        self.attempts: list[tuple] = []
        self._patches: list[tuple] = []

    def install(self) -> None:
        import socket

        try:
            import requests  # noqa: F401
        except ImportError:
            requests = None

        orig_socket_connect = socket.socket.connect
        orig_socket_connect_ex = socket.socket.connect_ex
        orig_getaddrinfo = socket.getaddrinfo

        def _blocked(*a, **kw):
            self.attempts.append(("socket", a, kw))
            raise AssertionError(
                f"network access blocked by NetworkBlocker: {a!r} {kw!r}"
            )

        socket.socket.connect = _blocked
        socket.socket.connect_ex = _blocked
        socket.getaddrinfo = _blocked
        self._patches.append(
            ("socket.connect", socket.socket, "connect", orig_socket_connect)
        )
        self._patches.append(
            ("socket.connect_ex", socket.socket, "connect_ex", orig_socket_connect_ex)
        )
        self._patches.append(
            ("socket.getaddrinfo", socket, "getaddrinfo", orig_getaddrinfo)
        )

        if requests is not None:
            orig_request = requests.Session.request

            def _blocked_request(*a, **kw):
                self.attempts.append(("requests", a, kw))
                raise AssertionError(
                    f"HTTP access blocked by NetworkBlocker: {a!r} {kw!r}"
                )

            requests.Session.request = _blocked_request
            self._patches.append(
                ("requests.Session.request", requests.Session, "request", orig_request)
            )

    def uninstall(self) -> None:
        for _name, obj, attr, orig in self._patches:
            setattr(obj, attr, orig)
        self._patches.clear()

    def __enter__(self):
        self.install()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.uninstall()
        return False


# ---------------------------------------------------------------------------
# DB blob scanner — assert no raw image/audio data is in the database
# ---------------------------------------------------------------------------
_IMAGE_MAGIC = (
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",  # JPEG
    b"GIF87a",
    b"GIF89a",
    b"BM",  # BMP (weak, checked by column context)
    b"RIFF",  # WEBP/WAV container
)

_IMAGE_BASE64_PREFIXES = (
    b"iVBORw0KGgo",  # PNG
    b"/9j/",  # JPEG
    b"R0lGOD",  # GIF
    b"UklGR",  # WEBP
)

_AUDIO_MAGIC = (
    b"ID3",  # MP3
    b"\xff\xfb",  # MP3 frame sync
    b"RIFF",  # WAV container
    b"OggS",  # OGG
    b"fLaC",  # FLAC
)


class DBBlobScanner:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def scan(self, kinds: tuple[str, ...] = ("image", "audio")) -> list[dict]:
        """Return a list of findings: {table, column, rowid, kind, match}."""
        findings: list[dict] = []
        tables = [
            r[0]
            for r in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        for table in tables:
            if table.startswith("sqlite_"):
                continue
            cols = self.conn.execute(f"PRAGMA table_info({table})").fetchall()
            text_cols = [c[1] for c in cols if c[2] in ("TEXT", "BLOB", "")]
            if not text_cols:
                continue
            for col in text_cols:
                try:
                    rows = self.conn.execute(
                        f"SELECT rowid, {col} FROM {table} " f"WHERE {col} IS NOT NULL"
                    ).fetchall()
                except sqlite3.OperationalError:
                    continue
                for rowid, value in rows:
                    if isinstance(value, str):
                        raw = value.encode("utf-8", errors="ignore")
                    elif isinstance(value, (bytes, bytearray)):
                        raw = bytes(value)
                    else:
                        continue
                    if "image" in kinds:
                        for magic in _IMAGE_MAGIC:
                            if raw.startswith(magic):
                                findings.append(
                                    {
                                        "table": table,
                                        "column": col,
                                        "rowid": rowid,
                                        "kind": "image",
                                        "match": magic[:8],
                                    }
                                )
                                break
                        for prefix in _IMAGE_BASE64_PREFIXES:
                            if prefix in raw[:64]:
                                findings.append(
                                    {
                                        "table": table,
                                        "column": col,
                                        "rowid": rowid,
                                        "kind": "image_base64",
                                        "match": prefix,
                                    }
                                )
                                break
                    if "audio" in kinds:
                        for magic in _AUDIO_MAGIC:
                            if raw.startswith(magic):
                                findings.append(
                                    {
                                        "table": table,
                                        "column": col,
                                        "rowid": rowid,
                                        "kind": "audio",
                                        "match": magic[:8],
                                    }
                                )
                                break
        return findings

    def assert_no_image_blobs(self) -> None:
        findings = self.scan(("image",))
        assert not findings, f"raw image data found in DB: {findings}"

    def assert_no_audio_blobs(self) -> None:
        findings = self.scan(("audio",))
        assert not findings, f"raw audio data found in DB: {findings}"

    def assert_clean(self) -> None:
        findings = self.scan(("image", "audio"))
        assert not findings, f"raw media found in DB: {findings}"


# ---------------------------------------------------------------------------
# Consent fake — for tests that need to grant/revoke rapidly
# ---------------------------------------------------------------------------
class FakeConsent:
    def __init__(self, granted: set[str] | None = None) -> None:
        self.granted = set(granted or ())
        self._lock = threading.Lock()

    def get_consent(self, channel: str) -> bool:
        with self._lock:
            return channel in self.granted

    def grant(self, channel: str) -> None:
        with self._lock:
            self.granted.add(channel)

    def revoke(self, channel: str) -> None:
        with self._lock:
            self.granted.discard(channel)


# ---------------------------------------------------------------------------
# Bundle — what the fixture yields
# ---------------------------------------------------------------------------
@dataclass
class Phase4Spies:
    fake_vlm: FakeVLM
    cloud_spy: CloudBackendSpy
    vision_router_spy: VisionRouterSpy
    network_blocker: NetworkBlocker
    clock: FakeClock
    consent: FakeConsent

    def db_scanner(self, conn: sqlite3.Connection) -> DBBlobScanner:
        return DBBlobScanner(conn)
