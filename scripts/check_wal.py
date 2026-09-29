"""Verify SQLite is in WAL mode."""

import sqlite3

from shadow.config import load_config

cfg = load_config()
conn = sqlite3.connect(cfg["memory"]["db_path"])
cur = conn.cursor()
cur.execute("PRAGMA journal_mode")
mode = cur.fetchone()[0]
cur.execute("PRAGMA synchronous")
sync = cur.fetchone()[0]
cur.execute("PRAGMA foreign_keys")
fk = cur.fetchone()[0]
print("journal_mode:", mode)
print("synchronous:", sync, "(1 = NORMAL)")
print("foreign_keys:", fk, "(1 = ON, 0 = OFF)")
conn.close()
