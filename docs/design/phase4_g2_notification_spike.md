# G2 — Windows Notification Content Access Spike (DR-P4-06)

Time-box: 2–3 days. Owner: <name>. Date: <date>.

## Question
Can a non-packaged desktop Python app on Windows 10/11 read OS notification
content safely, with explicit user permission, and without replying/dismissing?

## Candidate API
WinRT `UserNotificationListener` (Windows.UI.Notifications / Management).
Test via `winrt-runtime` + `winrt-Windows.UI.Notifications.Management`.

## Test matrix
| OS | Packaged (MSIX)? | Permission flow works? | Can read text? | Can filter by app? | Revocation works? | Notes |
|---|---|---|---|---|---|---|
| Win10 22H2 | No  | | | | | |
| Win10 22H2 | Yes | | | | | |
| Win11 23H2 | No  | | | | | |
| Win11 23H2 | Yes | | | | | |
| Win11 24H2 | No  | | | | | |
| Win11 24H2 | Yes | | | | | |

## Minimum viable script
```python
from winrt.windows.ui.notifications.management import UserNotificationListener, UserNotificationListenerAccessStatus
import asyncio

async def probe():
    listener = UserNotificationListener.current
    status = await listener.request_access_async()
    print("access:", status)
    if status != UserNotificationListenerAccessStatus.ALLOWED:
        return
    notes = await listener.get_notifications_async(0)  # 0 = all
    for n in notes[:5]:
        print(n.app_info.display_info.display_name, "|", n.notification.visual.bindings[0].get_text_elements()[0].text)

asyncio.run(probe())