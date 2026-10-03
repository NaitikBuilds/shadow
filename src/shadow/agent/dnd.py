"""Do Not Disturb — global toggle to silence notifications.

State persists in schema_meta. Toggling does not stop observation;
memory keeps filling. Users can still open panels manually.
"""

from PySide6.QtCore import QObject, Signal


class DoNotDisturb(QObject):
    """Tracks DND state and notifies listeners on change."""

    changed = Signal(bool)

    META_KEY = "dnd_enabled"

    def __init__(self, memory):
        super().__init__()
        self.memory = memory
        self._enabled = self._load()

    # ---------- public API ----------

    @property
    def enabled(self) -> bool:
        return self._enabled

    def toggle(self) -> bool:
        self.set(not self._enabled)
        return self._enabled

    def set(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self._enabled:
            return
        self._enabled = enabled
        self._save()
        try:
            self.memory.log_activity("dnd_change", "on" if enabled else "off")
        except Exception:
            pass
        self.changed.emit(enabled)

    # ---------- persistence ----------

    def _load(self) -> bool:
        try:
            value = self.memory.get_meta(self.META_KEY)
            return value == "1"
        except Exception:
            return False

    def _save(self) -> None:
        try:
            self.memory.set_meta(self.META_KEY, "1" if self._enabled else "0")
        except Exception:
            pass
