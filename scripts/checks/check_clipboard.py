"""Inspect clipboard observations and recent activity."""

import sqlite3

from shadow.config import load_config

cfg = load_config()
conn = sqlite3.connect(cfg["memory"]["db_path"])
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM observations WHERE source = 'clipboard'")
print("total clipboard observations:", cur.fetchone()[0])

cur.execute(
    "SELECT timestamp, substr(content, 1, 120) FROM observations "
    "WHERE source = 'clipboard' ORDER BY id DESC LIMIT 10"
)
print()
print("recent clipboard rows:")
for row in cur.fetchall():
    print(" ", row)

cur.execute("SELECT channel, enabled FROM consents WHERE channel = 'clipboard'")
print()
print("clipboard consent:", cur.fetchone())

conn.close()
