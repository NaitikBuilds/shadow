"""Tests for C11b: SHADOW self-observation guard."""

from __future__ import annotations

import pytest

from shadow.perception.self_guard import (
    is_shadow_process,
    is_shadow_text,
    is_shadow_title,
    is_shadow_window,
)

pytestmark = pytest.mark.p4


# --- process detection ---
@pytest.mark.parametrize(
    "proc",
    [
        "python.exe",
        "Python.EXE",
        "python3.exe",
        "pythonw.exe",
        "shadow.exe",
        "SHADOW.EXE",
        "shadow",
        "C:\\Python311\\python.exe",
        "C:\\Program Files\\SHADOW\\shadow.exe",
    ],
)
def test_self_process_names_match(proc):
    assert is_shadow_process(proc) is True


@pytest.mark.parametrize(
    "proc",
    [
        None,
        "",
        "chrome.exe",
        "code.exe",
        "notepad.exe",
        "node.exe",
        "jupyter-notebook.exe",
    ],
)
def test_non_self_process_names_rejected(proc):
    assert is_shadow_process(proc) is False


# --- title detection ---
@pytest.mark.parametrize(
    "title",
    [
        "SHADOW",
        "SHADOW — Main",
        "SHADOW — Vision",
        "SHADOW - Privacy",
        "Clone: test-quit",
        "Clone: what if",
        "Ethical Mirror",
        "Send this reflection to cloud?",
        "SHADOW — Diagnostics",
    ],
)
def test_shadow_titles_match(title):
    assert is_shadow_title(title) is True


@pytest.mark.parametrize(
    "title",
    [
        None,
        "",
        "Visual Studio Code",
        "Phase 4 planning - Chrome",
        "Some random SHADOW mention",
        "not a shadow window",
    ],
)
def test_non_shadow_titles_rejected(title):
    assert is_shadow_title(title) is False


# --- combined ---
def test_shadow_window_requires_both_conditions():
    # Both conditions -> True
    assert is_shadow_window({"process": "python.exe", "title": "Clone: x"}) is True
    # Process matches, title doesn't -> False (defence against excluding all Python)
    assert (
        is_shadow_window({"process": "python.exe", "title": "notebook.ipynb"}) is False
    )
    # Title matches, process doesn't -> False
    assert is_shadow_window({"process": "chrome.exe", "title": "SHADOW"}) is False
    # Neither -> False
    assert is_shadow_window({"process": "chrome.exe", "title": "Gmail"}) is False


def test_shadow_window_accepts_alternate_field_names():
    assert (
        is_shadow_window({"process_name": "python.exe", "window_title": "Clone: x"})
        is True
    )
    assert is_shadow_window({"exe": "python.exe", "title": "Ethical Mirror"}) is True


def test_shadow_window_empty_sample():
    assert is_shadow_window({}) is False


# --- text-level guard ---
@pytest.mark.parametrize(
    "text",
    [
        "SHADOW — Main",
        "Clone: test-quit SIMULATION — not part of your memory",
        "Send this reflection to cloud? Your values and this decision",
        "Ethical Mirror Setup Wizard",
    ],
)
def test_shadow_text_matches(text):
    assert is_shadow_text(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "",
        None,
        "Phase 4 planning",
        "VS Code — some_file.py",
    ],
)
def test_shadow_text_rejects_non_matches(text):
    assert is_shadow_text(text) is False
