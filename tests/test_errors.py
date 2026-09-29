import tempfile
from pathlib import Path

import pytest

from shadow.errors import ErrorReporter, Severity, ShadowError


@pytest.fixture
def reporter(tmp_path):
    return ErrorReporter(log_dir=tmp_path / "logs")


def test_severity_values():
    assert Severity.SILENT.value == "silent"
    assert Severity.BADGE.value == "badge"
    assert Severity.TRAY.value == "tray"
    assert Severity.MODAL.value == "modal"


def test_shadow_error_defaults():
    err = ShadowError(severity=Severity.SILENT, feature="test", reason="why")
    assert err.user_action == ""
    assert err.traceback_id == ""
    assert err.timestamp


def test_reporter_creates_log_dir(tmp_path):
    ErrorReporter(log_dir=tmp_path / "missing_dir")
    assert (tmp_path / "missing_dir").exists()


def test_silent_does_not_notify_tray_listener(reporter):
    received = []
    reporter.subscribe(Severity.TRAY, received.append)
    reporter.silent("test", "quiet failure")
    assert received == []


def test_tray_notifies_tray_listener(reporter):
    received = []
    reporter.subscribe(Severity.TRAY, received.append)
    reporter.tray("test", "needs attention")
    assert len(received) == 1
    assert received[0].severity == Severity.TRAY
    assert received[0].reason == "needs attention"


def test_badge_notifies_badge_listener(reporter):
    received = []
    reporter.subscribe(Severity.BADGE, received.append)
    reporter.badge("test", "transient")
    assert len(received) == 1


def test_modal_notifies_modal_listener(reporter):
    received = []
    reporter.subscribe(Severity.MODAL, received.append)
    reporter.modal("app", "fatal", user_action="Restart")
    assert len(received) == 1
    assert received[0].user_action == "Restart"


def test_traceback_id_assigned_when_exception(reporter):
    received = []
    reporter.subscribe(Severity.TRAY, received.append)
    try:
        raise ValueError("boom")
    except ValueError as exc:
        reporter.tray("test", "raised", exc=exc)
    assert received[0].traceback_id != ""


def test_traceback_written_to_file(reporter, tmp_path):
    try:
        raise RuntimeError("expected")
    except RuntimeError as exc:
        reporter.tray("test", "raised", exc=exc)

    logs = list((tmp_path / "logs").glob("errors_*.log"))
    assert len(logs) == 1
    content = logs[0].read_text(encoding="utf-8")
    assert "expected" in content
    assert "RuntimeError" in content


def test_listener_exception_does_not_break_reporter(reporter):
    def bad_listener(_err):
        raise RuntimeError("listener crashed")

    good_received = []
    reporter.subscribe(Severity.TRAY, bad_listener)
    reporter.subscribe(Severity.TRAY, good_received.append)

    reporter.tray("test", "should still work")
    assert len(good_received) == 1


def test_tray_batch_capped(tmp_path):
    reporter = ErrorReporter(log_dir=tmp_path / "logs", max_tray_batch=3)
    for i in range(5):
        reporter.tray("test", f"error {i}")
    assert len(reporter._recent_tray) == 3
    assert reporter._recent_tray[-1].reason == "error 4"


def test_memory_logging_optional(reporter):
    """No memory attached — should not raise."""
    reporter.tray("test", "no memory")
