import sqlite3

conn = sqlite3.connect("orders.db")
c = conn.cursor()

# Add drink_type column if missing
try:
    c.execute("ALTER TABLE orders ADD COLUMN drink_type TEXT")
    print("✅ Added 'drink_type' column")
except sqlite3.OperationalError:
    print("⚠️ 'drink_type' column already exists, skipped")

# Add phone column if missing
try:
    c.execute("ALTER TABLE orders ADD COLUMN phone TEXT")
    print("✅ Added 'phone' column")
except sqlite3.OperationalError:
    print("⚠️ 'phone' column already exists, skipped")

conn.commit()
conn.close()
print("✅ Database schema updated")
