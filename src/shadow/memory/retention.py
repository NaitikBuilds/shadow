"""Storage retention and pruning for SHADOW.

Runs at startup (at most once per configured interval). Handles:
  - Low-value observation pruning (empty, too short, unknown process)
  - Full observation pruning if user configures a retention window
  - Activity log rotation
  - Error log rotation
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path

from shadow.config import retention_config

log = logging.getLogger("shadow.retention")

# An observation shorter than this is a candidate for pruning.
MIN_MEANINGFUL_CHARS = 20

# Low-value content markers.
LOW_VALUE_MARKERS = ("unknown:", "unknown", "None")


class RetentionPolicy:
    def __init__(self, memory, config, log_dir: str | Path = "logs"):
        self.memory = memory
        self.pcfg = retention_config(config)
        self.log_dir = Path(log_dir)

    def maybe_run(self) -> dict | None:
        """Run pruning if the interval has elapsed. Returns summary or None."""
        interval_hours = self.pcfg["prune_interval_hours"]
        last = self.memory.get_meta("last_prune_at")
        if last:
            try:
                last_dt = datetime.fromisoformat(last)
                if datetime.utcnow() - last_dt < timedelta(hours=interval_hours):
                    return None
            except ValueError:
                pass

        summary = self.run()
        self.memory.set_meta(
            "last_prune_at", datetime.utcnow().isoformat(sep=" ", timespec="seconds")
        )
        self.memory.log_activity(
            "prune",
            (
                f"low_value={summary['low_value_deleted']}, "
                f"old={summary['old_deleted']}, "
                f"activity={summary['activity_deleted']}, "
                f"logs={summary['logs_deleted']}"
            ),
        )
        return summary

    def run(self) -> dict:
        return {
            "low_value_deleted": self._prune_low_value(),
            "old_deleted": self._prune_by_age(),
            "activity_deleted": self._prune_activity_log(),
            "logs_deleted": self._rotate_error_logs(),
        }

    # ---------- pruners ----------

    def _prune_low_value(self) -> int:
        days = self.pcfg["low_value_days"]
        if days <= 0:
            return 0
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat(
            sep=" ", timespec="seconds"
        )

        cur = self.memory.conn.cursor()
        # Find candidate IDs first (we need to delete from vec_observations too)
        cur.execute(
            """
            SELECT id, source, content
            FROM observations
            WHERE timestamp < ?
            """,
            (cutoff,),
        )
        candidates: list[int] = []
        for obs_id, source, content in cur.fetchall():
            text = (content or "").strip()
            if len(text) < MIN_MEANINGFUL_CHARS:
                candidates.append(obs_id)
                continue
            lower = text.lower()
            if source == "active_window" and any(
                lower.startswith(m) for m in LOW_VALUE_MARKERS
            ):
                candidates.append(obs_id)

        if not candidates:
            return 0

        with self.memory._lock:
            for chunk_start in range(0, len(candidates), 500):
                chunk = candidates[chunk_start : chunk_start + 500]
                placeholders = ",".join("?" * len(chunk))
                self.memory.conn.execute(
                    f"DELETE FROM vec_observations WHERE rowid IN ({placeholders})",
                    chunk,
                )
                self.memory.conn.execute(
                    f"DELETE FROM observation_entities WHERE observation_id IN ({placeholders})",
                    chunk,
                )
                self.memory.conn.execute(
                    f"DELETE FROM observations WHERE id IN ({placeholders})",
                    chunk,
                )
            self.memory.conn.commit()

        log.info("Pruned %d low-value observations", len(candidates))
        return len(candidates)

    def _prune_by_age(self) -> int:
        days = self.pcfg["observations_days"]
        if days <= 0:
            return 0
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat(
            sep=" ", timespec="seconds"
        )

        cur = self.memory.conn.cursor()
        cur.execute("SELECT id FROM observations WHERE timestamp < ?", (cutoff,))
        ids = [r[0] for r in cur.fetchall()]
        if not ids:
            return 0

        with self.memory._lock:
            for chunk_start in range(0, len(ids), 500):
                chunk = ids[chunk_start : chunk_start + 500]
                placeholders = ",".join("?" * len(chunk))
                self.memory.conn.execute(
                    f"DELETE FROM vec_observations WHERE rowid IN ({placeholders})",
                    chunk,
                )
                self.memory.conn.execute(
                    f"DELETE FROM observation_entities WHERE observation_id IN ({placeholders})",
                    chunk,
                )
                self.memory.conn.execute(
                    f"DELETE FROM observations WHERE id IN ({placeholders})",
                    chunk,
                )
            self.memory.conn.commit()

        log.info("Pruned %d old observations (older than %d days)", len(ids), days)
        return len(ids)

    def _prune_activity_log(self) -> int:
        days = self.pcfg["activity_days"]
        if days <= 0:
            return 0
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat(
            sep=" ", timespec="seconds"
        )

        cur = self.memory.conn.cursor()
        # Always keep the last 1000 entries regardless of age.
        cur.execute(
            "SELECT id FROM activity_log WHERE timestamp < ? "
            "AND id < (SELECT MAX(id) - 1000 FROM activity_log)",
            (cutoff,),
        )
        ids = [r[0] for r in cur.fetchall()]
        if not ids:
            return 0

        with self.memory._lock:
            placeholders = ",".join("?" * len(ids))
            self.memory.conn.execute(
                f"DELETE FROM activity_log WHERE id IN ({placeholders})", ids
            )
            self.memory.conn.commit()

        log.info("Pruned %d activity log rows", len(ids))
        return len(ids)

    def _rotate_error_logs(self) -> int:
        days = self.pcfg["error_logs_days"]
        if days <= 0 or not self.log_dir.exists():
            return 0
        cutoff = datetime.now() - timedelta(days=days)
        deleted = 0
        for path in self.log_dir.glob("errors_*.log"):
            try:
                # Filename format: errors_YYYYMMDD.log
                stamp = path.stem.split("_", 1)[1]
                file_date = datetime.strptime(stamp, "%Y%m%d")
                if file_date < cutoff:
                    path.unlink()
                    deleted += 1
            except (ValueError, OSError):
                continue
        if deleted:
            log.info("Deleted %d old error logs", deleted)
        return deleted
