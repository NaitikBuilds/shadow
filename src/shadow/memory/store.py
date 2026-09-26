import sqlite3
from pathlib import Path

import sqlite_vec


class MemoryStore:
    """Local SQLite + sqlite-vec memory for the Shadow."""

    def __init__(self, db_path: str, vector_dim: int = 384):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.enable_load_extension(True)
        sqlite_vec.load(self.conn)
        self.conn.enable_load_extension(False)
        self.vector_dim = vector_dim
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self.conn.cursor()
        cur.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                source TEXT,
                content TEXT,
                metadata TEXT
            );
            CREATE TABLE IF NOT EXISTS intentions (
                id INTEGER PRIMARY KEY,
                description TEXT,
                status TEXT,
                due DATETIME,
                confidence REAL
            );
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                action TEXT,
                details TEXT
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS vec_observations USING vec0(
                embedding float[{self.vector_dim}]
            );
            """
        )
        self.conn.commit()

    def add_observation(self, source: str, content: str, metadata: str = "") -> int:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO observations (source, content, metadata) VALUES (?, ?, ?)",
            (source, content, metadata),
        )
        self.conn.commit()
        return cur.lastrowid

    def add_embedding(self, rowid: int, embedding: list[float]) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO vec_observations (rowid, embedding) VALUES (?, ?)",
            (rowid, sqlite_vec.serialize_float32(embedding)),
        )
        self.conn.commit()

    def log_activity(self, action: str, details: str = "") -> None:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO activity_log (action, details) VALUES (?, ?)",
            (action, details),
        )
        self.conn.commit()

    def recent_activity(self, limit: int = 50) -> list[tuple]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT timestamp, action, details FROM activity_log "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return cur.fetchall()

    def wipe(self) -> None:
        cur = self.conn.cursor()
        cur.executescript(
            """
            DELETE FROM observations;
            DELETE FROM intentions;
            DELETE FROM activity_log;
            DELETE FROM vec_observations;
            """
        )
        self.conn.commit()

    def close(self) -> None:
        """Close the SQLite connection (required on Windows before deleting DB)."""
        try:
            self.conn.close()
        except Exception:  # noqa: BLE001
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()