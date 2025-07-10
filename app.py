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
            customer_name TEXT,
            drink_type TEXT,
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

    if request.method == "POST":
        name = request.form["name"]
        drink = request.form["drink"]
        tokens = int(request.form["tokens"])
        redeemed = 1 if "redeemed" in request.form else 0
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT INTO orders (customer_name, drink_type, tokens, redeemed, date) VALUES (?, ?, ?, ?, ?)",
                  (name, drink, tokens, redeemed, date))
        conn.commit()
        conn.close()
        return redirect("/")

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM orders ORDER BY date DESC")
    orders = c.fetchall()
    conn.close()
    return render_template("index.html", orders=orders)

@app.route("/export")
def export():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM orders", conn)
    conn.close()

    df["Today's Order"] = 1
    df["Redeemed"] = df["redeemed"].apply(lambda x: 1 if x else 0)

    template_file = "Bound Cafe Test 3.xlsm"
    wb = load_workbook(template_file, keep_vba=True)
    ws = wb["Sheet1"]

    start_row = 2
    for i, row in df.iterrows():
        ws.cell(row=start_row + i, column=1, value=row["customer_name"])
        # B left for manual Unique ID
        ws.cell(row=start_row + i, column=3, value=1)
        ws.cell(row=start_row + i, column=4, value=row["drink_type"])
        # E left for your Excel formula
        ws.cell(row=start_row + i, column=6, value=row["tokens"])
        ws.cell(row=start_row + i, column=7, value=f"{row['Redeemed']} / {row['tokens']}")

    export_file = "Bound Cafe Exported.xlsm"
    wb.save(export_file)
    return send_file(export_file, as_attachment=True)

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
