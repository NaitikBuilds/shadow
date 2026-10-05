"""Show the last 10 screen_uia and screen_ocr observations."""

import sqlite3

from shadow.config import load_config

cfg = load_config()
conn = sqlite3.connect(cfg["memory"]["db_path"])
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM observations WHERE source = 'screen_uia'")
print("screen_uia count:", cur.fetchone()[0])

cur.execute("SELECT COUNT(*) FROM observations WHERE source = 'screen_ocr'")
print("screen_ocr count:", cur.fetchone()[0])

print()
print("Last 10 screen observations:")
cur.execute(
    "SELECT timestamp, source, substr(content, 1, 160) "
    "FROM observations "
    "WHERE source IN ('screen_uia', 'screen_ocr') "
    "ORDER BY id DESC LIMIT 10"
)
for row in cur.fetchall():
    print(" ", row)

conn.close()
