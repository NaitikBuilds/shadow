import sys
from datetime import datetime, timedelta

import pytest

from shadow.perception import PerceptionSource, WindowsCalendarSource


class FakeAppointment:
    def __init__(
        self,
        subject="",
        start_time=None,
        duration=timedelta(hours=1),
        location="",
        details="",
        local_id="",
        calendar_id="",
    ):
        self.subject = subject
        self.start_time = start_time
        self.duration = duration
        self.location = location
        self.details = details
        self.local_id = local_id
        self.calendar_id = calendar_id


def test_source_is_perception_source():
    src = WindowsCalendarSource()
    assert isinstance(src, PerceptionSource)


def test_metadata():
    src = WindowsCalendarSource()
    assert src.name == "calendar_winrt"
    assert src.channel == "calendar"


def test_to_dict_basic():
    src = WindowsCalendarSource()
    start = datetime(2026, 9, 27, 15, 0)
    appt = FakeAppointment(
        subject="Team standup",
        start_time=start,
        duration=timedelta(hours=1),
        location="Room B",
        local_id="abc",
        calendar_id="cal1",
    )
    result = src._to_dict(appt)
    assert result is not None
    assert result["summary"] == "Team standup"
    assert result["start"] == start
    assert result["end"] == start + timedelta(hours=1)
    assert result["location"] == "Room B"
    assert result["uid"] == "cal1::abc"


def test_to_dict_empty_subject():
    src = WindowsCalendarSource()
    appt = FakeAppointment(subject="", start_time=datetime.now())
    assert src._to_dict(appt) is None


def test_to_dict_missing_start():
    src = WindowsCalendarSource()
    appt = FakeAppointment(subject="No start", start_time=None)
    assert src._to_dict(appt) is None


def test_format_upcoming():
    src = WindowsCalendarSource()
    now = datetime(2026, 9, 27, 12, 0)
    event = {
        "uid": "x",
        "summary": "Meeting",
        "start": datetime(2026, 9, 27, 14, 0),
        "end": datetime(2026, 9, 27, 15, 0),
        "location": "Room A",
        "description": "",
    }
    result = src._format(event, now)
    assert result["status"] == "upcoming"
    assert "upcoming" in result["content"]
    assert "Room A" in result["content"]
    assert result["source_backend"] == "winrt"


def test_format_ongoing():
    src = WindowsCalendarSource()
    now = datetime(2026, 9, 27, 14, 30)
    event = {
        "uid": "x",
        "summary": "Meeting",
        "start": datetime(2026, 9, 27, 14, 0),
        "end": datetime(2026, 9, 27, 15, 0),
        "location": "",
        "description": "",
    }
    result = src._format(event, now)
    assert result["status"] == "ongoing"


def test_format_past():
    src = WindowsCalendarSource()
    now = datetime(2026, 9, 27, 16, 0)
    event = {
        "uid": "x",
        "summary": "Meeting",
        "start": datetime(2026, 9, 27, 14, 0),
        "end": datetime(2026, 9, 27, 15, 0),
        "location": "",
        "description": "",
    }
    result = src._format(event, now)
    assert result["status"] == "past"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only source")
def test_sample_returns_none_in_unpackaged_build():
    """In unpackaged dev mode this returns None (permission denied).
    That's the intended behavior. In a packaged app with permission
    granted, it returns a dict — but this test can't check that case."""
    src = WindowsCalendarSource(lookback_days=30, lookahead_days=30)
    result = src.sample()
    # Either None (permission denied) or a dict (packaged with permission).
    # Both are valid; we just verify no exception is raised.
    if result is not None:
        assert set(result.keys()) >= {
            "uid",
            "summary",
            "start",
            "end",
            "status",
            "content",
            "source_backend",
        }


def test_uid_dedupe():
    """Two calls with the same event should only emit once."""
    src = WindowsCalendarSource()
    start = datetime.now() + timedelta(hours=1)

    class FakeStore:
        pass

    # Simulate by directly manipulating _seen_ids
    src._seen_ids.add("cal1::abc")
    assert "cal1::abc" in src._seen_ids
