# Calendar Test Fixtures

iCalendar (.ics) edge cases for the calendar source.

## Required files (to be added in Phase 3)

- `simple.ics` — basic upcoming event
- `timezone.ics` — event with TZID
- `all_day.ics` — all-day event (DATE not DATETIME)
- `recurring.ics` — RRULE event
- `no_summary.ics` — event without SUMMARY (should be skipped)
- `malformed.ics` — invalid syntax (should be skipped gracefully)