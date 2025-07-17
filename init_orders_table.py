import sqlite3

conn = sqlite3.connect("orders.db")
c = conn.cursor()

c.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        unique_id TEXT,
        customer_name TEXT,
        quantity INTEGER,
        tokens INTEGER,
        redeemed INTEGER,
        date TEXT,
        drink_type TEXT,
        phone TEXT
    )
""")

conn.commit()
conn.close()

print("✅ Created 'orders' table in orders.db")
