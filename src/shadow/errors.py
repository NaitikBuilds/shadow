"""SHADOW error taxonomy and reporting.

Every failure routes through an ErrorReporter instance. The reporter
classifies the error by severity, logs it (with traceback stored to disk,
never to the database or user content), records it to the activity log
if memory is attached, and dispatches it to any registered listeners.

Design goals:
  - No unhandled error should crash the app (except DB/model failures).
  - The user sees only what they can act on.
  - Tracebacks live in files, not in the DB or the UI.
  - Error reporting never leaks user content.
"""

from __future__ import annotations

import logging
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path


class Severity(StrEnum):
    SILENT = "silent"  # logged only
    BADGE = "badge"  # transient UI indicator
    TRAY = "tray"  # system tray notification
    MODAL = "modal"  # blocking dialog


@dataclass
class ShadowError:
    severity: Severity
    feature: str
    reason: str
    user_action: str = ""
    traceback_id: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.utcnow().isoformat(sep=" ", timespec="seconds")
    )


Listener = Callable[[ShadowError], None]


class ErrorReporter:
    """Central hub for error classification, logging, and routing.

    Listeners register per-severity. The reporter also keeps a small
    ring buffer of recent tray errors for UI batching (max 3 at a time).
    """

    def __init__(
        self,
        log_dir: str | Path = "logs",
        memory=None,
        max_tray_batch: int = 3,
    ):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.memory = memory
        self.max_tray_batch = max_tray_batch

        self._listeners: dict[Severity, list[Listener]] = {s: [] for s in Severity}
        self._recent_tray: list[ShadowError] = []
        self._logger = logging.getLogger("shadow.errors")

    # ---------- subscription ----------

    def subscribe(self, severity: Severity, listener: Listener) -> None:
        self._listeners[severity].append(listener)

    # ---------- convenience methods ----------

    def silent(self, feature: str, reason: str, exc: BaseException | None = None):
        self._emit(Severity.SILENT, feature, reason, exc=exc)

    def badge(
        self,
        feature: str,
        reason: str,
        user_action: str = "",
        exc: BaseException | None = None,
    ):
        self._emit(Severity.BADGE, feature, reason, user_action, exc)

    def tray(
        self,
        feature: str,
        reason: str,
        user_action: str = "",
        exc: BaseException | None = None,
    ):
        self._emit(Severity.TRAY, feature, reason, user_action, exc)

    def modal(
        self,
        feature: str,
        reason: str,
        user_action: str = "",
        exc: BaseException | None = None,
    ):
        self._emit(Severity.MODAL, feature, reason, user_action, exc)

    # ---------- core ----------

    def _emit(
        self,
        severity: Severity,
        feature: str,
        reason: str,
        user_action: str = "",
        exc: BaseException | None = None,
    ) -> ShadowError:
        tb_id = ""
        if exc is not None:
            stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            tb_id = f"{stamp}_{id(exc) & 0xFFFF:04x}"

        err = ShadowError(
            severity=severity,
            feature=feature,
            reason=reason,
            user_action=user_action,
            traceback_id=tb_id,
        )
        self.report(err, exc=exc)
        return err

    def report(self, error: ShadowError, exc: BaseException | None = None) -> None:
        self._log(error, exc)

        if self.memory is not None:
            try:
                self.memory.log_activity(
                    "error",
                    f"[{error.severity.value}] {error.feature}: {error.reason}",
                )
            except Exception:  # noqa: BLE001
                pass

        for listener in self._listeners[error.severity]:
            try:
                listener(error)
            except Exception:  # noqa: BLE001
                pass

        if error.severity == Severity.TRAY:
            self._recent_tray.append(error)
            while len(self._recent_tray) > self.max_tray_batch:
                self._recent_tray.pop(0)

    # ---------- logging ----------

    def _log(self, error: ShadowError, exc: BaseException | None) -> None:
        line = f"[{error.severity.value}] {error.feature}: {error.reason}"
        if error.traceback_id:
            line += f" (tb: {error.traceback_id})"
        self._logger.error(line)

        if exc is not None and error.traceback_id:
            tb_path = (
                self.log_dir / f"errors_{datetime.utcnow().strftime('%Y%m%d')}.log"
            )
            try:
                with open(tb_path, "a", encoding="utf-8") as f:
                    f.write(
                        f"\n=== {error.timestamp} | "
                        f"{error.traceback_id} | {error.feature} ===\n"
                    )
                    f.write(f"reason: {error.reason}\n")
                    f.write(
                        "".join(
                            traceback.format_exception(
                                type(exc), exc, exc.__traceback__
                            )
                        )
                    )
                    f.write("\n")
            except OSError:
                pass


def install_exception_hook(reporter: ErrorReporter) -> None:
    """Route unhandled exceptions in Qt slots / top-level through the reporter."""
    import sys

    original = sys.excepthook

    def _hook(exc_type, exc_value, exc_tb):
        reporter.modal(
            "app",
            f"Unhandled {exc_type.__name__}: {exc_value}",
            user_action="SHADOW may be unstable. Consider restarting.",
            exc=exc_value,
        )
        original(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook
