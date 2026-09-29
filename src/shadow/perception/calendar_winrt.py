import asyncio
import sys
from datetime import datetime, timedelta
from typing import Any

from .base import PerceptionSource


class WindowsCalendarSource(PerceptionSource):
    """Reads the Windows consolidated calendar store via WinRT.

    Requires the 'appointments' capability, which is only granted to
    packaged (MSIX) applications. For unpackaged development builds,
    permission is denied and sample() returns None silently. Once
    SHADOW ships as a packaged app, this source starts working without
    any code changes.
    """

    name = "calendar_winrt"
    channel = "calendar"

    def __init__(self, lookback_days: int = 1, lookahead_days: int = 14):
        self.lookback_days = lookback_days
        self.lookahead_days = lookahead_days
        self._seen_ids: set[str] = set()
        self._access_logged = False

    def sample(self) -> dict[str, Any] | None:
        if sys.platform != "win32":
            return None

        try:
            appointments = asyncio.run(self._load_appointments())
        except Exception as exc:  # noqa: BLE001
            if not self._access_logged:
                print(
                    "[calendar_winrt] inactive in unpackaged builds "
                    "(requires MSIX packaging; see docs/CALENDAR.md)",
                    file=sys.stderr,
                )
                self._access_logged = True
            return None

        if not appointments:
            return None

        now = datetime.now()
        for appt in appointments:
            uid = appt.get("uid") or ""
            if uid and uid in self._seen_ids:
                continue
            if uid:
                self._seen_ids.add(uid)
            return self._format(appt, now)

        return None

    # ---------- internals ----------

    async def _load_appointments(self) -> list[dict]:
        try:
            from winrt.windows.applicationmodel.appointments import (
                AppointmentManager,
                AppointmentStoreAccessType,
                FindAppointmentsOptions,
            )
        except ImportError:
            return []

        store = await AppointmentManager.request_store_async(
            AppointmentStoreAccessType.ALL_CALENDARS_READ_ONLY
        )
        if store is None:
            return []

        now = datetime.now()
        start = (now - timedelta(days=self.lookback_days)).astimezone()
        end = (now + timedelta(days=self.lookahead_days)).astimezone()

        options = None
        try:
            options = FindAppointmentsOptions()
            for prop in (
                "Subject",
                "StartTime",
                "Duration",
                "Location",
                "Details",
                "LocalId",
                "CalendarId",
            ):
                options.fetch_properties.append(prop)
        except Exception:  # noqa: BLE001
            options = None

        try:
            if options is not None:
                result = await store.find_appointments_async(start, end, options)
            else:
                result = await store.find_appointments_async(start, end)
        except TypeError:
            result = await store.find_appointments_async(start, end)

        raw = getattr(result, "appointments", result)
        parsed: list[dict] = []
        for appt in raw:
            d = self._to_dict(appt)
            if d:
                parsed.append(d)
        return parsed

    def _to_dict(self, appt) -> dict | None:
        try:
            subject = str(appt.subject or "").strip()
            if not subject:
                return None

            start = appt.start_time
            if start is None:
                return None
            duration = appt.duration or timedelta(0)

            if start.tzinfo:
                start = start.astimezone().replace(tzinfo=None)
            end = start + duration

            local_id = str(appt.local_id or "")
            calendar_id = str(appt.calendar_id or "")
            uid = f"{calendar_id}::{local_id}" if local_id else ""

            return {
                "uid": uid,
                "summary": subject,
                "start": start,
                "end": end,
                "location": str(appt.location or "").strip(),
                "description": str(appt.details or "").strip()[:500],
            }
        except Exception:  # noqa: BLE001
            return None

    def _format(self, event: dict, now: datetime) -> dict:
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
            "description": event["description"],
            "status": status,
            "content": content,
            "source_backend": "winrt",
            "timestamp": datetime.utcnow().isoformat(sep=" ", timespec="seconds"),
        }
