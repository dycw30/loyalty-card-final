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

    if request.method == "POST":
        unique_id = request.form["unique_id"]
        drink = request.form["drink"]
        quantity = int(request.form["quantity"])
        tokens = quantity // 9
        redeemed = int(request.form["redeem"]) if request.form.get("redeem") else 0
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        c.execute("INSERT INTO orders (unique_id, drink_type, quantity, tokens, redeemed, date) VALUES (?, ?, ?, ?, ?, ?)",
                  (unique_id, drink, quantity, tokens, redeemed, date))
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
    df = pd.read_sql_query("SELECT * FROM orders ORDER BY date", conn)
    conn.close()

    if df.empty:
        return "No data to export"

    # Write into Bound CRM Test 3.xlsm template
    template_file = "Bound CRM Test 3.xlsm"
    wb = load_workbook(template_file, keep_vba=True)
    ws = wb["Sheet1"]

    start_row = 2
    for i, row in df.iterrows():
        ws.cell(row=start_row + i, column=1, value=row["unique_id"])   # A
        # B left for your manual Unique ID / CRM
        ws.cell(row=start_row + i, column=3, value=row["quantity"])    # C Today's Order
        ws.cell(row=start_row + i, column=4, value=row["drink_type"])  # D
        # Columns E, F (Tokens), G left to be calculated by your Excel formulas

    output_file = "Bound Cafe Exported.xlsm"
    wb.save(output_file)
    return send_file(output_file, as_attachment=True)

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
