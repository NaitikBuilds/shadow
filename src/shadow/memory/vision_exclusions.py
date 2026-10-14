"""Persistent per-app vision exclusions.

Replaces session-scoped exclusions in VisionOfferPolicy. Excluded
processes are never offered vision, never analyzed by Ctrl+Shift+V,
never captured by image file ingestion, and never passed to the
sensitive-window filter.
"""



class VisionExclusionStore:
    """Read/write access to vision_exclusions."""

    def __init__(self, memory):
        self.memory = memory

    # ---------- queries ----------

    def is_excluded(self, process: str) -> bool:
        key = self._normalize(process)
        if not key:
            return False
        try:
            cur = self.memory.conn.cursor()
            cur.execute(
                "SELECT 1 FROM vision_exclusions WHERE process = ?",
                (key,),
            )
            return cur.fetchone() is not None
        except Exception:
            return False

    def all_excluded(self) -> list[dict]:
        try:
            cur = self.memory.conn.cursor()
            cur.execute(
                "SELECT process, reason, added_at FROM vision_exclusions "
                "ORDER BY added_at DESC"
            )
            return [
                {"process": r[0], "reason": r[1] or "", "added_at": r[2]}
                for r in cur.fetchall()
            ]
        except Exception:
            return []

    def count(self) -> int:
        try:
            cur = self.memory.conn.cursor()
            cur.execute("SELECT COUNT(*) FROM vision_exclusions")
            return int(cur.fetchone()[0] or 0)
        except Exception:
            return 0

    # ---------- writes ----------

    def exclude(self, process: str, reason: str = "user") -> bool:
        key = self._normalize(process)
        if not key:
            return False
        try:
            with self.memory._lock:
                cur = self.memory.conn.cursor()
                cur.execute(
                    "INSERT OR IGNORE INTO vision_exclusions "
                    "(process, reason) VALUES (?, ?)",
                    (key, reason),
                )
                self.memory.conn.commit()
            try:
                self.memory.log_activity("vision_exclude", f"{key} ({reason})")
            except Exception:
                pass
            return True
        except Exception:
            return False

    def include(self, process: str) -> bool:
        key = self._normalize(process)
        if not key:
            return False
        try:
            with self.memory._lock:
                cur = self.memory.conn.cursor()
                cur.execute(
                    "DELETE FROM vision_exclusions WHERE process = ?",
                    (key,),
                )
                self.memory.conn.commit()
            try:
                self.memory.log_activity("vision_include", key)
            except Exception:
                pass
            return True
        except Exception:
            return False

    def clear_all(self) -> int:
        try:
            with self.memory._lock:
                cur = self.memory.conn.cursor()
                cur.execute("DELETE FROM vision_exclusions")
                deleted = cur.rowcount
                self.memory.conn.commit()
            return deleted
        except Exception:
            return 0

    # ---------- internals ----------

    @staticmethod
    def _normalize(process: str) -> str:
        if not process:
            return ""
        import os
        filename = os.path.basename(process)
        return filename.strip().lower().replace(".exe", "")
