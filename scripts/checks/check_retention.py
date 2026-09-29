"""Verify retention and crash recovery state after startup."""

from shadow.config import load_config
from shadow.memory import MemoryStore

cfg = load_config()
store = MemoryStore(cfg["memory"]["db_path"])
try:
    print("last_prune_at:", store.get_meta("last_prune_at"))

    cur = store.conn.cursor()
    cur.execute("SELECT COUNT(*) FROM activity_log WHERE action = 'prune'")
    print("prune entries in log:", cur.fetchone()[0])

    cur.execute("SELECT COUNT(*) FROM activity_log WHERE action = 'crash_recovered'")
    print("crash_recovered entries:", cur.fetchone()[0])

    cur.execute("SELECT COUNT(*) FROM observations")
    print("total observations:", cur.fetchone()[0])

    cur.execute("SELECT COUNT(*) FROM vec_observations")
    print("total embeddings:", cur.fetchone()[0])
finally:
    store.close()
