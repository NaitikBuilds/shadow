"""Self-tests: prove the C02 harness works before Phase 4 features use it.

If any of these fail, EVERY later privacy test inherits the bug. This file
must be green before C03 ships.
"""

from __future__ import annotations

import base64
import sqlite3

import pytest

from tests._phase4_spies import (
    CloudBackendSpy,
    DBBlobScanner,
    FakeClock,
    FakeConsent,
    FakeVLM,
    NetworkBlocker,
    Spy,
)

pytestmark = pytest.mark.p4_privacy


# ---------------------------------------------------------------------------
# Spy basics
# ---------------------------------------------------------------------------
def test_spy_records_and_asserts():
    s = Spy("x")
    s(1, 2, k=3)
    s(4)
    assert s.called()
    assert s.called_times() == 2
    s.assert_called_times(2)
    s.assert_called_with(1, 2)
    s.reset()
    s.assert_not_called()


def test_spy_assert_not_called_fails_when_called():
    s = Spy("x")
    s()
    with pytest.raises(AssertionError, match="called 1 times, expected 0"):
        s.assert_not_called()


# ---------------------------------------------------------------------------
# FakeVLM
# ---------------------------------------------------------------------------
def test_fake_vlm_deterministic():
    vlm = FakeVLM(default_caption="default")
    assert vlm.caption(b"x") == "default"
    vlm.set_response("a", "b")
    assert vlm.caption(b"x") == "a"
    assert vlm.caption(b"x") == "b"
    assert vlm.caption(b"x") == "default"
    assert len(vlm.calls) == 4


# ---------------------------------------------------------------------------
# CloudBackendSpy
# ---------------------------------------------------------------------------
def test_cloud_spy_assert_not_called_passes_when_untouched():
    spy = CloudBackendSpy()
    spy.assert_not_called()


def test_cloud_spy_detects_call():
    spy = CloudBackendSpy()
    spy.understand_image(b"img")
    with pytest.raises(AssertionError):
        spy.assert_not_called()


def test_cloud_spy_detects_unknown_attr():
    spy = CloudBackendSpy()
    spy.some_new_method("x")  # recorded via __getattr__
    with pytest.raises(AssertionError):
        spy.assert_not_called()


# ---------------------------------------------------------------------------
# FakeClock
# ---------------------------------------------------------------------------
def test_fake_clock_advance():
    c = FakeClock(start=1_700_000_000.0)
    t0 = c.now()
    c.advance(600)
    assert c.now() - t0 == 600
    assert c.now_utc().tzinfo is not None


# ---------------------------------------------------------------------------
# NetworkBlocker
# ---------------------------------------------------------------------------
def test_network_blocker_blocks_socket():
    blocker = NetworkBlocker()
    with blocker, pytest.raises(AssertionError, match="network access blocked"):
        import socket

        socket.socket().connect(("1.1.1.1", 443))
    # After exit, normal sockets still work (we don't actually connect here).


def test_network_blocker_blocks_requests_session():
    requests = pytest.importorskip("requests")
    blocker = NetworkBlocker()
    with blocker, pytest.raises(AssertionError, match="HTTP access blocked"):
        requests.Session().request("GET", "http://example.com")
    assert any(kind == "requests" for kind, *_ in blocker.attempts)


# ---------------------------------------------------------------------------
# DBBlobScanner
# ---------------------------------------------------------------------------
def _make_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE observations (id INTEGER PRIMARY KEY, text TEXT, blob BLOB)"
    )
    conn.commit()
    return conn


def test_db_scanner_clean_on_text_only():
    conn = _make_conn()
    conn.execute("INSERT INTO observations(text) VALUES ('safe text')")
    conn.commit()
    DBBlobScanner(conn).assert_clean()


def test_db_scanner_detects_png():
    conn = _make_conn()
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    conn.execute("INSERT INTO observations(blob) VALUES (?)", (png,))
    conn.commit()
    with pytest.raises(AssertionError, match="image"):
        DBBlobScanner(conn).assert_no_image_blobs()


def test_db_scanner_detects_base64_png():
    conn = _make_conn()
    b64 = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32).decode()
    conn.execute("INSERT INTO observations(text) VALUES (?)", (b64,))
    conn.commit()
    with pytest.raises(AssertionError, match="image"):
        DBBlobScanner(conn).assert_no_image_blobs()


def test_db_scanner_detects_mp3():
    conn = _make_conn()
    mp3 = b"ID3\x04\x00\x00" + b"\x00" * 32
    conn.execute("INSERT INTO observations(blob) VALUES (?)", (mp3,))
    conn.commit()
    with pytest.raises(AssertionError, match="audio"):
        DBBlobScanner(conn).assert_no_audio_blobs()


# ---------------------------------------------------------------------------
# FakeConsent
# ---------------------------------------------------------------------------
def test_fake_consent_grant_revoke():
    c = FakeConsent()
    assert not c.get_consent("vision")
    c.grant("vision")
    assert c.get_consent("vision")
    c.revoke("vision")
    assert not c.get_consent("vision")


# ---------------------------------------------------------------------------
# Fixture integration
# ---------------------------------------------------------------------------
def test_phase4_spies_fixture_bundle(phase4_spies):
    assert phase4_spies.fake_vlm.caption(b"x") is not None
    phase4_spies.cloud_spy.assert_not_called()
    phase4_spies.consent.grant("vision")
    assert phase4_spies.consent.get_consent("vision")
    scanner = phase4_spies.db_scanner(_make_conn())
    scanner.assert_clean()


# ---------------------------------------------------------------------------
# Markers must be registered
# ---------------------------------------------------------------------------
def test_markers_are_registered(request):
    """If pyproject.toml / pytest.ini forgot the markers, pytest warns loudly."""
    markers = request.config.getini("markers") or []
    names = [m.split(":")[0].strip() for m in markers]
    assert "p4" in names, f"marker 'p4' not registered; found: {names}"
    assert "p4_privacy" in names, f"marker 'p4_privacy' not registered; found: {names}"
