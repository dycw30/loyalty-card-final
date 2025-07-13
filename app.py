from flask import Flask, render_template, request, redirect, send_file, session, url_for
import sqlite3
from datetime import datetime
import os
import pandas as pd
from openpyxl import load_workbook

app = Flask(__name__)
app.secret_key = 'supersecretkey'
DB_NAME = "orders.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Orders table with barista_name
    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unique_id TEXT,
            drink_type TEXT,
            quantity INTEGER,
            tokens INTEGER,
            redeemed INTEGER,
            barista_name TEXT,
            date TEXT
        )
    """)
    
    # Baristas table
    c.execute("""
        CREATE TABLE IF NOT EXISTS baristas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    """)
    conn.commit()

    # Insert default baristas if table is empty
    c.execute("SELECT COUNT(*) FROM baristas")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO baristas (username, password) VALUES (?, ?)", [
            ('david', 'coffee123'),
            ('alice', 'latte456'),
            ('bob', 'mocha789')
        ])
        conn.commit()

    # Check if barista_name column exists, add if missing
    c.execute("PRAGMA table_info(orders)")
    columns = [col[1] for col in c.fetchall()]
    if 'barista_name' not in columns:
        c.execute("ALTER TABLE orders ADD COLUMN barista_name TEXT")
        conn.commit()

    conn.close()

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT * FROM baristas WHERE username=? AND password=?", (username, password))
        user = c.fetchone()
        conn.close()

        if user:
            session["logged_in"] = True
            session["barista"] = username
            return redirect(url_for("index"))
        else:
            return render_template("login.html", error="Invalid credentials")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/", methods=["GET", "POST"])
def index():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    summary = {}
    top_customers = []
    top_drinks = []

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    if request.method == "POST":
        unique_id = request.form["unique_id"]
        drink = request.form["drink"]
        quantity = int(request.form["quantity"])
        tokens = quantity // 9
        redeemed = int(request.form["redeem"]) if request.form.get("redeem") else 0
        barista_name = session.get("barista")
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        c.execute("INSERT INTO orders (unique_id, drink_type, quantity, tokens, redeemed, barista_name, date) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (unique_id, drink, quantity, tokens, redeemed, barista_name, date))
        conn.commit()

    # Dashboard summary
    c.execute("SELECT COUNT(DISTINCT unique_id), SUM(quantity), SUM(redeemed) FROM orders")
    result = c.fetchone()
    total_orders = result[1] or 0
    total_tokens = total_orders // 9
    summary = {
        "total_customers": result[0] or 0,
        "total_tokens": total_tokens,
        "total_redeemed": result[2] or 0,
        "balance_tokens": total_tokens - (result[2] or 0)
    }

    # Top Unique IDs
    c.execute("""
        SELECT unique_id, SUM(quantity) / 9 as tokens
        FROM orders
        GROUP BY unique_id
        ORDER BY tokens DESC
        LIMIT 5
    """)
    top_customers = [(row[0], int(row[1])) for row in c.fetchall()]

    # Top Drinks
    c.execute("""
        SELECT drink_type, SUM(quantity)
        FROM orders
        GROUP BY drink_type
        ORDER BY SUM(quantity) DESC
        LIMIT 5
    """)
    top_drinks = c.fetchall()

    conn.close()

    return render_template("index.html", summary=summary, top_customers=top_customers, top_drinks=top_drinks)

@app.route("/export")
def export():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("""
        SELECT unique_id,
               SUM(quantity) AS total_orders,
               SUM(quantity) / 9 AS total_tokens,
               SUM(redeemed) AS total_redeemed,
               (SUM(quantity) / 9) - SUM(redeemed) AS balance
        FROM orders
        GROUP BY unique_id
    """, conn)
    conn.close()

    if df.empty:
        return "No data to export"

    template_file = "Bound CRM Test 3.xlsm"
    wb = load_workbook(template_file, keep_vba=True)
    ws = wb["Sheet1"]

    start_row = 2
    for i, row in df.iterrows():
        ws.cell(row=start_row + i, column=1, value=row["unique_id"])
        ws.cell(row=start_row + i, column=3, value=int(row["total_orders"]))

    output_file = "Bound Cafe Aggregated Export.xlsm"
    wb.save(output_file)
    return send_file(output_file, as_attachment=True)

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
