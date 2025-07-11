from flask import Flask, render_template, request, redirect, send_file, session, url_for
import sqlite3
from datetime import datetime
import os
import pandas as pd
from openpyxl import Workbook

app = Flask(__name__)
app.secret_key = 'supersecretkey'
DB_NAME = "orders.db"

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
            date TEXT
        )
    """)
    conn.commit()
    conn.close()

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        if username == "admin" and password == "coffee123":
            session["logged_in"] = True
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

    totals = None
    summary = {}
    top_customers = []
    top_drinks = []

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Handle new order
    if request.method == "POST":
        unique_id = request.form["unique_id"]
        drink = request.form["drink"]
        quantity = int(request.form["quantity"])
        tokens_per_order = 1
        tokens = quantity * tokens_per_order
        redeemed = int(request.form["redeem"]) if request.form.get("redeem") else 0
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        c.execute("INSERT INTO orders (unique_id, drink_type, quantity, tokens, redeemed, date) VALUES (?, ?, ?, ?, ?, ?)",
                  (unique_id, drink, quantity, tokens, redeemed, date))
        conn.commit()

    # Dashboard summary
    c.execute("SELECT COUNT(DISTINCT unique_id), SUM(tokens), SUM(redeemed) FROM orders")
    result = c.fetchone()
    summary = {
        "total_customers": result[0] or 0,
        "total_tokens": result[1] or 0,
        "total_redeemed": result[2] or 0,
        "balance_tokens": (result[1] or 0) - (result[2] or 0)
    }

    # Top Unique IDs
    c.execute("""
        SELECT unique_id, SUM(tokens) as total_tokens
        FROM orders
        GROUP BY unique_id
        ORDER BY total_tokens DESC
        LIMIT 5
    """)
    top_customers = c.fetchall()

    # Top Drinks
    c.execute("""
        SELECT drink_type, SUM(quantity) as total_qty
        FROM orders
        GROUP BY drink_type
        ORDER BY total_qty DESC
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
               SUM(quantity) as total_orders,
               SUM(tokens) as total_tokens,
               SUM(redeemed) as total_redeemed,
               (SUM(tokens) - SUM(redeemed)) as balance
        FROM orders
        GROUP BY unique_id
    """, conn)
    conn.close()

    if df.empty:
        return "No data to export"

    # Write to Excel
    output_file = "Cafe Loyalty Aggregated.xlsx"
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="Summary", index=False)

    return send_file(output_file, as_attachment=True)

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
