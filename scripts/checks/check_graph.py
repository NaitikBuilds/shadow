"""Quick graph inspection for development."""

import sqlite3

conn = sqlite3.connect("data/shadow.db")
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM entities")
print("entities:", cur.fetchone()[0])

cur.execute("SELECT COUNT(*) FROM edges")
print("edges:", cur.fetchone()[0])

cur.execute(
    "SELECT type, name, mention_count FROM entities "
    "ORDER BY mention_count DESC LIMIT 15"
)
for row in cur.fetchall():
    print(" ", row)

conn.close()
