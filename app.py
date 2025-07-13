from flask import Flask, render_template, request, redirect, send_file, session, url_for
import sqlite3
from datetime import datetime
import os
import pandas as pd
from openpyxl import load_workbook

app = Flask(__name__)
app.secret_key = 'supersecretkey'
DB_NAME = "orders.db"
ADMIN_PASS = "adminpass2025"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

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
    c.execute("""
        CREATE TABLE IF NOT EXISTS baristas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    """)
    conn.commit()

    c.execute("SELECT COUNT(*) FROM baristas")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO baristas (username, password) VALUES (?, ?)", [
            ('david', 'coffee123'),
            ('alice', 'latte456'),
            ('bob', 'mocha789')
        ])
        conn.commit()

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

    summary, top_customers, top_drinks = {}, [], []
    error = None

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    if request.method == "POST":
        unique_id = request.form["unique_id"]
        drink = request.form.get("drink") or None  # optional
        quantity = int(request.form["quantity"]) if request.form.get("quantity") else 0
        tokens = quantity // 9
        redeemed = int(request.form["redeem"]) if request.form.get("redeem") else 0
        barista_name = session.get("barista")
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Calculate current tokens balance
        c.execute("""
            SELECT COALESCE(SUM(quantity), 0) / 9 AS total_tokens,
                   COALESCE(SUM(redeemed), 0) AS total_redeemed
            FROM orders
            WHERE unique_id = ?
        """, (unique_id,))
        result = c.fetchone()
        total_tokens = int(result[0])
        total_redeemed = int(result[1])
        balance = total_tokens - total_redeemed

        if redeemed > balance:
            error = f"Cannot redeem {redeemed} tokens. Only {balance} tokens available."
        else:
            c.execute("INSERT INTO orders (unique_id, drink_type, quantity, tokens, redeemed, barista_name, date) VALUES (?, ?, ?, ?, ?, ?, ?)",
                      (unique_id, drink, quantity, tokens, redeemed, barista_name, date))
            conn.commit()
            return redirect("/")

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

    c.execute("""
        SELECT unique_id, SUM(quantity) / 9 as tokens
        FROM orders
        GROUP BY unique_id
        ORDER BY tokens DESC
        LIMIT 5
    """)
    top_customers = [(row[0], int(row[1])) for row in c.fetchall()]

    c.execute("""
        SELECT drink_type, SUM(quantity)
        FROM orders
        WHERE drink_type IS NOT NULL
        GROUP BY drink_type
        ORDER BY SUM(quantity) DESC
        LIMIT 5
    """)
    top_drinks = c.fetchall()

    conn.close()
    return render_template("index.html", summary=summary, top_customers=top_customers, top_drinks=top_drinks, error=error)

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

    wb = load_workbook("Bound CRM Test 3.xlsm", keep_vba=True)
    ws = wb["Sheet1"]
    start_row = 2
    for i, row in df.iterrows():
        ws.cell(row=start_row + i, column=1, value=row["unique_id"])
        ws.cell(row=start_row + i, column=3, value=int(row["total_orders"]))
    wb.save("Bound Cafe Aggregated Export.xlsm")
    return send_file("Bound Cafe Aggregated Export.xlsm", as_attachment=True)

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        master_password = request.form.get("master_password")
        if master_password != ADMIN_PASS:
            return render_template("admin.html", error="Invalid admin password", baristas=[])

        username = request.form.get("username")
        password = request.form.get("password")
        if username and password:
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            try:
                c.execute("INSERT INTO baristas (username, password) VALUES (?, ?)", (username, password))
                conn.commit()
            except sqlite3.IntegrityError:
                pass
            conn.close()

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT username FROM baristas")
    baristas = [row[0] for row in c.fetchall()]
    conn.close()
    return render_template("admin.html", baristas=baristas)

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
