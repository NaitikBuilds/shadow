"""Inspect typing_dynamics observations."""

import sqlite3

conn = sqlite3.connect("data/shadow.db")
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM observations WHERE source = 'typing_dynamics'")
print("typing observations:", cur.fetchone()[0])

cur.execute(
    "SELECT timestamp, substr(content, 1, 140) FROM observations "
    "WHERE source = 'typing_dynamics' ORDER BY id DESC LIMIT 5"
)
for row in cur.fetchall():
    print(row)

conn.close()
