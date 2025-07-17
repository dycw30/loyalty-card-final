import sqlite3
import os

# Delete existing DB if exists
if os.path.exists("users.db"):
    os.remove("users.db")
    print("🗑️ Removed existing users.db")

# Connect to a fresh DB
conn = sqlite3.connect("users.db")
c = conn.cursor()

# Create the users table
c.execute("""
    CREATE TABLE users (
        username TEXT PRIMARY KEY,
        password TEXT NOT NULL
    )
""")
print("✅ Created users table")

# Add default users
users = [
    ("admin", "adminpass"),
    ("barista1", "coffee123")
]

c.executemany("INSERT INTO users (username, password) VALUES (?, ?)", users)

conn.commit()
conn.close()
print("✅ Added default users: admin, barista1")
