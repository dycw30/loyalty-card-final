import sqlite3

conn = sqlite3.connect("users.db")
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password TEXT NOT NULL
)
""")
c.execute("INSERT OR IGNORE INTO users (username, password) VALUES (?, ?)", ("admin", "coffee123"))
conn.commit()
conn.close()

print("✅ users.db initialized with admin user.")
