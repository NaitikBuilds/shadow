import sqlite3
from pathlib import Path

import sqlite_vec


class MemoryStore:
    """Local SQLite + sqlite-vec memory for the Shadow."""

    def __init__(self, db_path: str, vector_dim: int = 384):
        import threading

        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.enable_load_extension(True)
        sqlite_vec.load(self.conn)
        self.conn.enable_load_extension(False)
        self.vector_dim = vector_dim
        self._lock = threading.RLock()
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self.conn.cursor()
        cur.executescript(f"""
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
            CREATE TABLE IF NOT EXISTS consents (
                channel TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 0,
                scope TEXT DEFAULT 'global',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS consent_audit (
                id INTEGER PRIMARY KEY,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                channel TEXT,
                action TEXT,
                reason TEXT
            );
                        CREATE TABLE IF NOT EXISTS entities (
                id INTEGER PRIMARY KEY,
                type TEXT NOT NULL,
                name TEXT NOT NULL,
                first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                mention_count INTEGER DEFAULT 1,
                UNIQUE(type, name)
            );
            CREATE TABLE IF NOT EXISTS edges (
                id INTEGER PRIMARY KEY,
                source_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                relation TEXT NOT NULL,
                weight REAL DEFAULT 1.0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source_id, target_id, relation),
                FOREIGN KEY(source_id) REFERENCES entities(id) ON DELETE CASCADE,
                FOREIGN KEY(target_id) REFERENCES entities(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS observation_entities (
                observation_id INTEGER NOT NULL,
                entity_id INTEGER NOT NULL,
                PRIMARY KEY (observation_id, entity_id),
                FOREIGN KEY(observation_id) REFERENCES observations(id) ON DELETE CASCADE,
                FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
            CREATE INDEX IF NOT EXISTS idx_obs_entities_obs ON observation_entities(observation_id);
            CREATE INDEX IF NOT EXISTS idx_obs_entities_ent ON observation_entities(entity_id); 
            """)
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
        with self._lock:
            cur = self.conn.cursor()
            cur.executescript("""
                DELETE FROM observation_entities;
                DELETE FROM edges;
                DELETE FROM entities;
                DELETE FROM vec_observations;
                DELETE FROM observations;
                DELETE FROM intentions;
                DELETE FROM activity_log;
                """)
            self.conn.commit()

        # ---------- knowledge graph ----------

    def upsert_entity(self, entity_type: str, name: str) -> int:
        """Insert or bump an entity. Returns its id."""
        name = name.strip()
        if not name:
            raise ValueError("entity name cannot be empty")
        with self._lock:
            cur = self.conn.cursor()
            cur.execute(
                """
                INSERT INTO entities (type, name) VALUES (?, ?)
                ON CONFLICT(type, name) DO UPDATE SET
                    last_seen = CURRENT_TIMESTAMP,
                    mention_count = mention_count + 1
                """,
                (entity_type, name),
            )
            self.conn.commit()
            cur.execute(
                "SELECT id FROM entities WHERE type = ? AND name = ?",
                (entity_type, name),
            )
            row = cur.fetchone()
            return int(row[0])

    def link_entity_to_observation(self, observation_id: int, entity_id: int) -> None:
        with self._lock:
            cur = self.conn.cursor()
            cur.execute(
                "INSERT OR IGNORE INTO observation_entities "
                "(observation_id, entity_id) VALUES (?, ?)",
                (observation_id, entity_id),
            )
            self.conn.commit()

    def add_edge(
        self,
        source_id: int,
        target_id: int,
        relation: str,
        weight: float = 1.0,
    ) -> None:
        """Create or strengthen an edge. Weight accumulates."""
        if source_id == target_id:
            return
        with self._lock:
            cur = self.conn.cursor()
            cur.execute(
                """
                INSERT INTO edges (source_id, target_id, relation, weight)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(source_id, target_id, relation) DO UPDATE SET
                    weight = weight + excluded.weight
                """,
                (source_id, target_id, relation, weight),
            )
            self.conn.commit()

    def entity_by_name(self, entity_type: str, name: str) -> dict | None:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, type, name, mention_count, first_seen, last_seen "
            "FROM entities WHERE type = ? AND name = ?",
            (entity_type, name),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "type": row[1],
            "name": row[2],
            "mention_count": row[3],
            "first_seen": row[4],
            "last_seen": row[5],
        }

    def entities_for_observation(self, observation_id: int) -> list[dict]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT e.id, e.type, e.name
            FROM observation_entities oe
            JOIN entities e ON e.id = oe.entity_id
            WHERE oe.observation_id = ?
            """,
            (observation_id,),
        )
        return [{"id": r[0], "type": r[1], "name": r[2]} for r in cur.fetchall()]

    def neighbors(self, entity_id: int, limit: int = 20) -> list[dict]:
        """Return entities connected to the given entity in either direction."""
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT e.id, e.type, e.name, ed.relation, ed.weight, 'out' AS direction
            FROM edges ed JOIN entities e ON e.id = ed.target_id
            WHERE ed.source_id = ?
            UNION ALL
            SELECT e.id, e.type, e.name, ed.relation, ed.weight, 'in' AS direction
            FROM edges ed JOIN entities e ON e.id = ed.source_id
            WHERE ed.target_id = ?
            ORDER BY weight DESC
            LIMIT ?
            """,
            (entity_id, entity_id, limit),
        )
        return [
            {
                "id": r[0],
                "type": r[1],
                "name": r[2],
                "relation": r[3],
                "weight": r[4],
                "direction": r[5],
            }
            for r in cur.fetchall()
        ]

    def recent_entities(self, limit: int = 30) -> list[dict]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, type, name, mention_count, last_seen "
            "FROM entities ORDER BY last_seen DESC LIMIT ?",
            (limit,),
        )
        return [
            {
                "id": r[0],
                "type": r[1],
                "name": r[2],
                "mention_count": r[3],
                "last_seen": r[4],
            }
            for r in cur.fetchall()
        ]

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

    def seed_consents(self, channels: list[str]) -> None:
        """Ensure every channel has a row. Missing rows default to disabled."""
        cur = self.conn.cursor()
        for ch in channels:
            cur.execute(
                "INSERT OR IGNORE INTO consents (channel, enabled) VALUES (?, 0)",
                (ch,),
            )
        self.conn.commit()

    def set_consent(self, channel: str, enabled: bool, reason: str = "") -> None:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO consents (channel, enabled, updated_at) "
            "VALUES (?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(channel) DO UPDATE SET "
            "enabled = excluded.enabled, updated_at = CURRENT_TIMESTAMP",
            (channel, 1 if enabled else 0),
        )
        cur.execute(
            "INSERT INTO consent_audit (channel, action, reason) VALUES (?, ?, ?)",
            (channel, "enable" if enabled else "disable", reason),
        )
        self.conn.commit()

    def get_consent(self, channel: str) -> bool:
        cur = self.conn.cursor()
        cur.execute("SELECT enabled FROM consents WHERE channel = ?", (channel,))
        row = cur.fetchone()
        return bool(row[0]) if row else False

    def all_consents(self) -> dict[str, bool]:
        cur = self.conn.cursor()
        cur.execute("SELECT channel, enabled FROM consents")
        return {ch: bool(en) for ch, en in cur.fetchall()}

    def consent_audit(self, limit: int = 100) -> list[tuple]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT timestamp, channel, action, reason FROM consent_audit "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return cur.fetchall()

    def search_similar(self, embedding: list[float], limit: int = 5) -> list[tuple]:
        """Return [(observation_id, content, timestamp, source, distance)]."""
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT o.id, o.content, o.timestamp, o.source, v.distance
            FROM vec_observations v
            JOIN observations o ON o.id = v.rowid
            WHERE v.embedding MATCH ? AND k = ?
            ORDER BY v.distance
            """,
            (sqlite_vec.serialize_float32(embedding), limit),
        )
        return cur.fetchall()

    def observations_between(self, start: str, end: str) -> list[tuple]:
        """Return [(id, timestamp, source, content)] between two ISO datetimes."""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, timestamp, source, content FROM observations "
            "WHERE timestamp BETWEEN ? AND ? ORDER BY timestamp DESC",
            (start, end),
        )
        return cur.fetchall()
