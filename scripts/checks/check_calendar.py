"""Inspect calendar observations."""

import sqlite3

conn = sqlite3.connect("data/shadow.db")
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM observations WHERE source = 'calendar'")
print("calendar observations:", cur.fetchone()[0])

cur.execute(
    "SELECT timestamp, substr(content, 1, 160) FROM observations "
    "WHERE source = 'calendar' ORDER BY id DESC LIMIT 10"
)
for row in cur.fetchall():
    print(row)

conn.close()
