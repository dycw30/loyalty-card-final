import sqlite3

# Connect or create the users.db
conn = sqlite3.connect("users.db")
c = conn.cursor()

# Create the users table
c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        password TEXT NOT NULL
    )
""")

# Insert default users
default_users = [
    ('admin', 'adminpass'),
    ('barista1', 'coffee123'),
    ('barista2', 'latte456')
]

for user in default_users:
    c.execute("INSERT OR REPLACE INTO users (username, password) VALUES (?, ?)", user)

conn.commit()
conn.close()

print("✅ users.db created with default users.")
