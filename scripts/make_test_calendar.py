"""Generate a test .ics file in Documents for calendar ingestion testing."""

from datetime import datetime, timedelta
from pathlib import Path

HOME = Path.home()
TARGET = HOME / "Documents" / "shadow_calendar_test.ics"

now = datetime.now()
events = [
    {
        "uid": "shadow-test-1",
        "summary": "SHADOW test meeting",
        "start": now + timedelta(hours=1),
        "end": now + timedelta(hours=2),
        "location": "Online",
    },
    {
        "uid": "shadow-test-2",
        "summary": "Review Phase 2",
        "start": now + timedelta(days=1),
        "end": now + timedelta(days=1, hours=1),
    },
    {
        "uid": "shadow-test-3",
        "summary": "Standup",
        "start": now + timedelta(hours=4),
        "end": now + timedelta(hours=4, minutes=15),
    },
]

lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//SHADOW//Test//EN"]
for e in events:
    lines.extend(
        [
            "BEGIN:VEVENT",
            f"UID:{e['uid']}",
            f"SUMMARY:{e['summary']}",
            f"DTSTART:{e['start'].strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{e['end'].strftime('%Y%m%dT%H%M%S')}",
        ]
    )
    if e.get("location"):
        lines.append(f"LOCATION:{e['location']}")
    lines.append("END:VEVENT")
lines.append("END:VCALENDAR")

TARGET.write_text("\n".join(lines), encoding="utf-8")
print(f"Wrote {TARGET}")
print(f"Events: {len(events)}")
