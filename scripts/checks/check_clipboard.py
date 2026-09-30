"""Inspect clipboard observations."""

import sqlite3

from shadow.config import load_config

cfg = load_config()
conn = sqlite3.connect(cfg["memory"]["db_path"])
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM observations WHERE source = 'clipboard'")
print("clipboard observations:", cur.fetchone()[0])
cur.execute(
    "SELECT timestamp, substr(content, 1, 120) FROM observations "
    "WHERE source = 'clipboard' ORDER BY id DESC LIMIT 5"
)
for row in cur.fetchall():
    print(row)
conn.close()
