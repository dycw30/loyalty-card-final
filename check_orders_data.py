import sqlite3

conn = sqlite3.connect("orders.db")
c = conn.cursor()

print("\n📊 Current data in orders.db:\n")
print("Unique ID | Name | Qty | Tokens | Redeemed | Drink | Phone | Date")
print("-" * 80)

for row in c.execute("""
    SELECT unique_id, customer_name, quantity, tokens, redeemed, drink_type, phone, date
    FROM orders
    ORDER BY unique_id
"""):
    print(row)

conn.close()
print("\n✅ Done reading database.\n")
