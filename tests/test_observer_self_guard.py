"""Tests for C11b: observer self-guard wiring."""

from __future__ import annotations

import pytest

from shadow.perception.observer import ObservationWorker
from shadow.perception.screen_vision import ScreenVisionSource
from shadow.perception.self_guard import is_shadow_window

pytestmark = pytest.mark.p4


# --- minimal worker for _do_tick tests ---
def _minimal_worker():
    w = ObservationWorker.__new__(ObservationWorker)
    w.pcfg = {"idle_skip_sec": 300, "ocr_every_n_ticks": 0}
    emitted = []

    class Sig:
        def __init__(self, name):
            self._name = name

        def emit(self, *a, **k):
            emitted.append((self._name, a))

    w.skipped = Sig("skipped")
    w.error = Sig("error")
    w.observation = Sig("observation")
    w.tick = Sig("tick")
    w._user_idle_too_long = lambda: False
    w._emitted = emitted

    added = []

    class Mem:
        def get_consent(self, _ch):
            return True

        def add_observation(self, src, content, metadata=None):
            added.append((src, content))
            return len(added)

    w.memory = Mem()
    w._added = added

    w.sources = []
    w.change_detector = type("C", (), {"has_changed": lambda s: True})()
    return w


# --- _do_tick early-skip on SHADOW window ---
def test_do_tick_skips_when_active_window_is_shadow(monkeypatch):
    w = _minimal_worker()
    with monkeypatch.context() as m:
        m.setattr(
            "shadow.perception.active_window.ActiveWindowSource.sample",
            lambda self: {"process": "python.exe", "title": "Clone: test-quit"},
        )
        w._do_tick()
    assert w._added == []
    assert any(name == "skipped" for name, _ in w._emitted)


def test_do_tick_skips_when_cloud_preview_open(monkeypatch):
    w = _minimal_worker()
    with monkeypatch.context() as m:
        m.setattr(
            "shadow.perception.active_window.ActiveWindowSource.sample",
            lambda self: {
                "process": "python.exe",
                "title": "Send this reflection to cloud?",
            },
        )
        w._do_tick()
    assert w._added == []


def test_do_tick_proceeds_when_active_window_is_external(monkeypatch):
    """Control: external window does not trigger the early skip."""
    w = _minimal_worker()
    with monkeypatch.context() as m:
        m.setattr(
            "shadow.perception.active_window.ActiveWindowSource.sample",
            lambda self: {"process": "chrome.exe", "title": "GitHub"},
        )
        w._do_tick()
    # No self_guard skip emitted. (Observation may or may not fire — that's
    # covered by other observer tests.)
    self_guard_skips = [
        args
        for name, args in w._emitted
        if name == "skipped" and args and "self_guard" in str(args)
    ]
    assert self_guard_skips == []


# --- _content_from header guard ---
def test_content_from_returns_empty_for_shadow_window():
    w = ObservationWorker.__new__(ObservationWorker)
    result = w._content_from(
        "active_window",
        {"process": "python.exe", "title": "Clone: test-quit"},
    )
    assert result == ""


def test_content_from_returns_empty_for_wizard():
    w = ObservationWorker.__new__(ObservationWorker)
    result = w._content_from(
        "screen_uia",
        {"process": "python.exe", "title": "Ethical Mirror Setup"},
    )
    assert result == ""


def test_content_from_proceeds_for_non_shadow():
    w = ObservationWorker.__new__(ObservationWorker)
    # Seed the subset of pcfg that _content_from consults for active_window.
    w.pcfg = {"min_title_length": 4, "max_title_length": 200}
    result = w._content_from(
        "active_window",
        {"process": "chrome.exe", "title": "GitHub — PR #42"},
    )
    # Guard did NOT return ""; _content_from built real content for the window.
    assert result != ""


# --- screen_vision _is_sensitive ---
def test_is_sensitive_true_for_shadow_window():
    assert (
        ScreenVisionSource._is_sensitive(
            {
                "process": "python.exe",
                "title": "SHADOW — Vision",
            }
        )
        is True
    )


def test_is_sensitive_true_for_clone_window():
    assert (
        ScreenVisionSource._is_sensitive(
            {
                "process": "python.exe",
                "title": "Clone: my-test",
            }
        )
        is True
    )


def test_is_sensitive_false_for_normal_window():
    assert (
        ScreenVisionSource._is_sensitive(
            {
                "process": "chrome.exe",
                "title": "GitHub — PR #42",
            }
        )
        is False
    )


# --- guard module invariants (regression on the fix) ---
def test_guard_does_not_exclude_all_python():
    """A Python notebook is not SHADOW."""
    assert (
        is_shadow_window({"process": "python.exe", "title": "notebook.ipynb"}) is False
    )


def test_guard_does_not_exclude_chrome_with_shadow_title():
    """A web page mentioning SHADOW is not SHADOW."""
    assert is_shadow_window({"process": "chrome.exe", "title": "SHADOW"}) is False
