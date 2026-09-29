"""Apply versioned SQL migrations to the SHADOW database."""

import re
import sqlite3
from datetime import datetime
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent
VERSION_KEY = "current_version"
BACKUP_RETENTION = 3


class MigrationError(RuntimeError):
    """Raised when a migration fails. Startup should refuse to continue."""


class MigrationRunner:
    """Discovers, orders, and applies .sql migrations.

    Design notes:
      - Migrations are forward-only. No rollback scripts.
      - Each migration runs via executescript(), which auto-commits per
        statement. Migrations are written idempotently (IF NOT EXISTS) so
        partial application is harmless on retry.
      - The version is only bumped after a migration succeeds. On failure,
        the DB stays at the previous version and startup should abort.
      - Before any pending migrations run, the DB is backed up. Last 3
        backups are retained.
    """

    def __init__(self, conn: sqlite3.Connection, db_path: str | Path):
        self.conn = conn
        self.db_path = Path(db_path)
        self.backup_dir = self.db_path.parent / "backups"

    def run(self) -> int:
        """Apply pending migrations. Returns the final version."""
        self._ensure_schema_meta()
        current = self._get_version()
        pending = [(v, p) for v, p in self._discover() if v > current]

        if not pending:
            return current

        self._backup(current)
        for version, path in pending:
            self._apply(path, version)
            current = version

        return current

    # ---------- meta table ----------

    def _ensure_schema_meta(self) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS schema_meta ("
            "  key TEXT PRIMARY KEY,"
            "  value TEXT"
            ")"
        )
        self.conn.commit()

    def _get_version(self) -> int:
        cur = self.conn.cursor()
        cur.execute("SELECT value FROM schema_meta WHERE key = ?", (VERSION_KEY,))
        row = cur.fetchone()
        if not row:
            return 0
        try:
            return int(row[0])
        except (TypeError, ValueError):
            return 0

    def _set_version(self, version: int) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO schema_meta (key, value) VALUES (?, ?)",
            (VERSION_KEY, str(version)),
        )
        self.conn.commit()

    # ---------- migration discovery ----------

    def _discover(self) -> list[tuple[int, Path]]:
        found: list[tuple[int, Path]] = []
        for path in MIGRATIONS_DIR.glob("*.sql"):
            match = re.match(r"^(\d+)_", path.name)
            if not match:
                continue
            found.append((int(match.group(1)), path))
        return sorted(found)

    # ---------- apply ----------

    def _apply(self, path: Path, version: int) -> None:
        sql = path.read_text(encoding="utf-8")
        try:
            self.conn.executescript(sql)
            self._set_version(version)
        except Exception as exc:
            raise MigrationError(
                f"Migration {path.name} (version {version}) failed: {exc}"
            ) from exc

    # ---------- backup ----------

    def _backup(self, current_version: int) -> None:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = self.backup_dir / f"shadow_v{current_version}_{ts}.db"

        try:
            dst = sqlite3.connect(str(target))
            self.conn.backup(dst)
            dst.close()
        except Exception:
            # Backup failure should not block migrations — log and continue.
            return

        self._prune_backups()

    def _prune_backups(self) -> None:
        backups = sorted(self.backup_dir.glob("shadow_v*.db"))
        for old in backups[:-BACKUP_RETENTION]:
            try:
                old.unlink()
            except OSError:
                pass
