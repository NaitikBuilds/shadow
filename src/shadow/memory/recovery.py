"""Crash recovery and startup consistency for SHADOW.

Runs at startup before any user-facing component loads. Detects unexpected
shutdowns, repairs orphan observations, and reports a summary.
"""

import logging
from datetime import datetime, timedelta

from shadow.config import retention_config

log = logging.getLogger("shadow.recovery")

# After this many hours without an embedding, try to re-embed an observation.
REEMBED_AFTER_HOURS = 24

# After this many hours, give up and drop the observation if re-embedding fails.
DROP_AFTER_HOURS = 72


class CrashRecovery:
    def __init__(self, memory, backend, config):
        self.memory = memory
        self.backend = backend
        self.pcfg = retention_config(config)

    def run_startup_recovery(self) -> dict:
        summary = {
            "shutdown_status": self._detect_shutdown(),
            "orphans_reembedded": 0,
            "orphans_dropped": 0,
        }

        if summary["shutdown_status"] == "unexpected":
            log.warning("Previous SHADOW session ended unexpectedly")
            try:
                self.memory.log_activity(
                    "crash_recovered",
                    "Previous session did not shut down cleanly",
                )
            except Exception:  # noqa: BLE001
                pass

        reembedded, dropped = self._recover_orphans()
        summary["orphans_reembedded"] = reembedded
        summary["orphans_dropped"] = dropped

        if reembedded or dropped:
            try:
                self.memory.log_activity(
                    "orphans_recovered",
                    f"reembedded={reembedded}, dropped={dropped}",
                )
            except Exception:  # noqa: BLE001
                pass

        return summary

    # ---------- internals ----------

    def _detect_shutdown(self) -> str:
        """Return 'first_run' | 'clean' | 'unexpected' | 'unknown'."""
        try:
            cur = self.memory.conn.cursor()
            cur.execute(
                "SELECT action FROM activity_log "
                "WHERE action IN ('app_start', 'app_stop') "
                "ORDER BY id DESC LIMIT 2"
            )
            rows = [r[0] for r in cur.fetchall()]
        except Exception:  # noqa: BLE001
            return "unknown"

        if not rows:
            return "first_run"
        if rows[0] == "app_stop":
            return "clean"
        if rows[0] == "app_start":
            return "unexpected"
        return "unknown"

    def _recover_orphans(self) -> tuple[int, int]:
        """Observations without embeddings. Re-embed if fresh; drop if very old."""
        cutoff_reembed = (
            datetime.utcnow() - timedelta(hours=REEMBED_AFTER_HOURS)
        ).isoformat(sep=" ", timespec="seconds")
        cutoff_drop = (datetime.utcnow() - timedelta(hours=DROP_AFTER_HOURS)).isoformat(
            sep=" ", timespec="seconds"
        )

        try:
            cur = self.memory.conn.cursor()
            cur.execute(
                """
                SELECT o.id, o.content, o.timestamp
                FROM observations o
                LEFT JOIN vec_observations v ON v.rowid = o.id
                WHERE v.rowid IS NULL AND o.timestamp < ?
                """,
                (cutoff_reembed,),
            )
            orphans = cur.fetchall()
        except Exception:  # noqa: BLE001
            return (0, 0)

        reembedded = 0
        dropped = 0
        for obs_id, content, timestamp in orphans:
            text = (content or "").strip()
            if not text:
                self._drop_observation(obs_id)
                dropped += 1
                continue

            # Try to re-embed if we still have the model and it's not too old
            if timestamp >= cutoff_drop:
                try:
                    vec = self.backend.embed(text)
                    self.memory.add_embedding(obs_id, vec)
                    reembedded += 1
                    continue
                except Exception:  # noqa: BLE001
                    log.warning("Re-embed failed for observation %d", obs_id)

            # Too old or embedding failed
            self._drop_observation(obs_id)
            dropped += 1

        return (reembedded, dropped)

    def _drop_observation(self, obs_id: int) -> None:
        with self.memory._lock:
            self.memory.conn.execute(
                "DELETE FROM observation_entities WHERE observation_id = ?",
                (obs_id,),
            )
            self.memory.conn.execute("DELETE FROM observations WHERE id = ?", (obs_id,))
            self.memory.conn.commit()
