# Calendar Ingestion

SHADOW has two calendar sources, both gated by the `calendar` consent channel.

## 1. WindowsCalendarSource (native, preferred)

Reads the Windows consolidated calendar store via the WinRT
`Windows.ApplicationModel.Appointments` API. This is the same store the
Windows Calendar app uses, so it can see Outlook, Google, and other
accounts the user has added to Windows.

**Permission model:** The API requires the `appointments` capability,
which is only granted to packaged (MSIX) applications. SHADOW is
currently distributed as a plain Python install for development, so
permission is denied and this source returns `None` on every tick.

Once SHADOW ships as a packaged MSIX app with the `appointments`
capability declared in its manifest, this source starts working with
zero code changes. That packaging step is planned for Phase 6.

## 2. CalendarSource (.ics fallback)

Reads `.ics` files from configured folders (`~/Documents`,
`~/Downloads` by default). Works for any user who manually exports
their calendar, and works regardless of packaging or permissions.

This source is a permanent fallback — it stays even after the WinRT
source becomes active, because some users will decline calendar
permission or continue to use unpackaged builds.

## How they coexist

Both sources register when `calendar` consent is granted. Each tick,
they run independently:

- If WinRT access is granted: it emits one event per tick.
- The `.ics` source emits one event per tick from files.

There is no deduplication between the two — if a user has the same
event synced both to Windows Calendar and to an `.ics` file, SHADOW
will record it twice. This is acceptable: the knowledge graph will
merge them via co-occurring entities, and the redundancy provides
resilience.

## Roadmap

- **Phase 2 (current):** Both sources ship. WinRT no-ops in unpackaged builds.
- **Phase 6:** MSIX packaging + `appointments` capability declaration.
  WinRT source activates automatically for packaged installs.