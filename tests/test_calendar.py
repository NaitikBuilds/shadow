from datetime import datetime, timedelta
from pathlib import Path

import pytest

from shadow.perception import CalendarSource, PerceptionSource


def ics_dt(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def write_ics(folder: Path, filename: str, events: list[dict]):
    parts = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//SHADOW//Test//EN"]
    for e in events:
        parts.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{e['uid']}",
                f"SUMMARY:{e['summary']}",
                f"DTSTART:{e['start']}",
                f"DTEND:{e['end']}",
            ]
        )
        if e.get("location"):
            parts.append(f"LOCATION:{e['location']}")
        parts.append("END:VEVENT")
    parts.append("END:VCALENDAR")
    (folder / filename).write_text("\n".join(parts), encoding="utf-8")


def test_source_is_perception_source(tmp_path):
    src = CalendarSource([str(tmp_path)])
    assert isinstance(src, PerceptionSource)


def test_metadata(tmp_path):
    src = CalendarSource([str(tmp_path)])
    assert src.name == "calendar"
    assert src.channel == "calendar"


def test_no_files_returns_none(tmp_path):
    src = CalendarSource([str(tmp_path)])
    assert src.sample() is None


def test_upcoming_event_ingested(tmp_path):
    now = datetime.now()
    start = now + timedelta(hours=2)
    end = start + timedelta(hours=1)

    write_ics(
        tmp_path,
        "cal.ics",
        [
            {
                "uid": "evt-1",
                "summary": "Team standup",
                "start": ics_dt(start),
                "end": ics_dt(end),
                "location": "Conference Room B",
            }
        ],
    )

    src = CalendarSource([str(tmp_path)])
    result = src.sample()
    assert result is not None
    assert result["summary"] == "Team standup"
    assert result["status"] == "upcoming"
    assert "Conference Room B" in result["content"]
    assert result["source_backend"] == "ics"


def test_ongoing_event_status(tmp_path):
    now = datetime.now()
    start = now - timedelta(minutes=15)
    end = now + timedelta(minutes=15)

    write_ics(
        tmp_path,
        "cal.ics",
        [
            {
                "uid": "evt-2",
                "summary": "Live call",
                "start": ics_dt(start),
                "end": ics_dt(end),
            }
        ],
    )

    src = CalendarSource([str(tmp_path)])
    result = src.sample()
    assert result is not None
    assert result["status"] == "ongoing"


def test_event_not_repeated(tmp_path):
    now = datetime.now()
    start = now + timedelta(hours=3)
    end = start + timedelta(hours=1)

    write_ics(
        tmp_path,
        "cal.ics",
        [
            {
                "uid": "evt-3",
                "summary": "One-shot",
                "start": ics_dt(start),
                "end": ics_dt(end),
            }
        ],
    )

    src = CalendarSource([str(tmp_path)])
    assert src.sample() is not None
    assert src.sample() is None


def test_far_future_event_ignored(tmp_path):
    now = datetime.now()
    start = now + timedelta(days=90)
    end = start + timedelta(hours=1)

    write_ics(
        tmp_path,
        "cal.ics",
        [
            {
                "uid": "evt-4",
                "summary": "Way out",
                "start": ics_dt(start),
                "end": ics_dt(end),
            }
        ],
    )

    src = CalendarSource([str(tmp_path)], lookahead_days=14)
    assert src.sample() is None


def test_far_past_event_ignored(tmp_path):
    now = datetime.now()
    start = now - timedelta(days=30)
    end = start + timedelta(hours=1)

    write_ics(
        tmp_path,
        "cal.ics",
        [
            {
                "uid": "evt-5",
                "summary": "Long ago",
                "start": ics_dt(start),
                "end": ics_dt(end),
            }
        ],
    )

    src = CalendarSource([str(tmp_path)], lookback_days=1)
    assert src.sample() is None


def test_multiple_events_one_at_a_time(tmp_path):
    now = datetime.now()
    events = [
        {
            "uid": f"m-{i}",
            "summary": f"Event {i}",
            "start": ics_dt(now + timedelta(hours=i + 1)),
            "end": ics_dt(now + timedelta(hours=i + 2)),
        }
        for i in range(3)
    ]
    write_ics(tmp_path, "cal.ics", events)

    src = CalendarSource([str(tmp_path)])
    got = []
    for _ in range(5):
        r = src.sample()
        if r is None:
            break
        got.append(r["summary"])

    assert len(got) == 3
    assert got == ["Event 0", "Event 1", "Event 2"]


def test_event_without_summary_skipped(tmp_path):
    now = datetime.now()
    write_ics(
        tmp_path,
        "cal.ics",
        [
            {
                "uid": "empty",
                "summary": "",
                "start": ics_dt(now + timedelta(hours=1)),
                "end": ics_dt(now + timedelta(hours=2)),
            }
        ],
    )
    src = CalendarSource([str(tmp_path)])
    assert src.sample() is None


def test_nonexistent_folder_safe(tmp_path):
    src = CalendarSource([str(tmp_path / "nope")])
    assert src.sample() is None
