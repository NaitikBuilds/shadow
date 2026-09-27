from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .base import PerceptionSource


class CalendarSource(PerceptionSource):
    """Reads .ics calendar files and emits events as observations.

    Each tick emits one event that hasn't been seen yet, from the time
    window [now - lookback_days, now + lookahead_days].
    """

    name = "calendar"
    channel = "calendar"

    def __init__(
        self,
        watch_folders: list[str],
        lookback_days: int = 1,
        lookahead_days: int = 14,
    ):
        self.watch_folders = [
            Path(f).expanduser().resolve() for f in watch_folders if f
        ]
        self.lookback_days = lookback_days
        self.lookahead_days = lookahead_days
        self._seen_uids: set[str] = set()

    def sample(self) -> dict[str, Any] | None:
        events = self._load_events()
        if not events:
            return None

        now = datetime.now()
        window_start = now - timedelta(days=self.lookback_days)
        window_end = now + timedelta(days=self.lookahead_days)

        def sort_key(e):
            start = e["start"]
            return (1, start) if start < now else (0, start)

        for event in sorted(events, key=sort_key):
            uid = event.get("uid") or ""
            if uid and uid in self._seen_uids:
                continue
            start = event.get("start")
            if start is None:
                continue
            if start < window_start or start > window_end:
                continue
            if uid:
                self._seen_uids.add(uid)
            return self._format_event(event, now)

        return None

    # ---------- internals ----------

    def _load_events(self) -> list[dict]:
        try:
            from icalendar import Calendar
        except ImportError:
            return []

        events: list[dict] = []
        for folder in self.watch_folders:
            if not folder.exists():
                continue
            for path in folder.rglob("*.ics"):
                try:
                    with open(path, "rb") as f:
                        cal = Calendar.from_ical(f.read())
                except Exception:  # noqa: BLE001
                    continue
                for component in cal.walk("VEVENT"):
                    parsed = self._component_to_dict(component)
                    if parsed:
                        events.append(parsed)
        return events

    def _component_to_dict(self, component) -> dict | None:
        try:
            uid = str(component.get("UID") or "")
            summary = str(component.get("SUMMARY") or "").strip()
            if not summary:
                return None

            dtstart = component.get("DTSTART")
            if dtstart is None:
                return None
            dtend = component.get("DTEND")

            start = dtstart.dt
            end = dtend.dt if dtend is not None else start

            if not isinstance(start, datetime):
                start = datetime.combine(start, datetime.min.time())
            if not isinstance(end, datetime):
                end = datetime.combine(end, datetime.min.time())

            if start.tzinfo:
                start = start.astimezone().replace(tzinfo=None)
            if end.tzinfo:
                end = end.astimezone().replace(tzinfo=None)

            return {
                "uid": uid,
                "summary": summary,
                "start": start,
                "end": end,
                "location": str(component.get("LOCATION") or "").strip(),
                "description": str(component.get("DESCRIPTION") or "").strip(),
            }
        except Exception:  # noqa: BLE001
            return None

    def _format_event(self, event: dict, now: datetime) -> dict:
        start = event["start"]
        end = event["end"]

        if now < start:
            status = "upcoming"
        elif now > end:
            status = "past"
        else:
            status = "ongoing"

        content = (
            f"Calendar event ({status}): {event['summary']} "
            f"from {start.strftime('%Y-%m-%d %H:%M')} "
            f"to {end.strftime('%Y-%m-%d %H:%M')}"
        )
        if event["location"]:
            content += f" at {event['location']}"

        return {
            "uid": event["uid"],
            "summary": event["summary"],
            "start": start.isoformat(sep=" ", timespec="minutes"),
            "end": end.isoformat(sep=" ", timespec="minutes"),
            "location": event["location"],
            "description": event["description"][:500],
            "status": status,
            "content": content,
            "source_backend": "ics",
            "timestamp": datetime.utcnow().isoformat(sep=" ", timespec="seconds"),
        }
