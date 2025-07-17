import sqlite3

conn = sqlite3.connect("users.db")
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL
)
""")

# Insert default user
c.execute("INSERT OR IGNORE INTO users (username, password) VALUES (?, ?)", ("admin", "adminpass"))
conn.commit()
conn.close()

print("✅ users.db created with default admin login")
