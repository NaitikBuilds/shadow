"""Verify the DB schema version and that data is preserved after migration."""

from shadow.config import load_config
from shadow.memory import MemoryStore

cfg = load_config()
store = MemoryStore(cfg["memory"]["db_path"])
try:
    cur = store.conn.cursor()

    cur.execute("SELECT value FROM schema_meta WHERE key = 'current_version'")
    row = cur.fetchone()
    print("schema version:", row[0] if row else "missing")

    cur.execute("SELECT COUNT(*) FROM observations")
    print("observations preserved:", cur.fetchone()[0])

    cur.execute("SELECT COUNT(*) FROM entities")
    print("entities preserved:", cur.fetchone()[0])

    cur.execute("SELECT COUNT(*) FROM consents")
    print("consent rows:", cur.fetchone()[0])
finally:
    store.close()
