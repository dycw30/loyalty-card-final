# [app.py]
from flask import Flask, render_template, request, redirect, session, url_for, send_file, jsonify
import sqlite3
from datetime import datetime
import pandas as pd
import os

app = Flask(__name__)
app.secret_key = 'supersecretkey'
DB_NAME = "orders.db"
USERS_DB = "users.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
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
    c.execute("""
        CREATE TABLE IF NOT EXISTS drinks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
    """)
    c.execute("INSERT OR IGNORE INTO drinks (name) VALUES ('Latte'), ('Espresso'), ('Cappuccino')")
    conn.commit()
    conn.close()

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        conn = sqlite3.connect(USERS_DB)
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
        user = c.fetchone()
        conn.close()
        if user:
            session["username"] = username
            session["logged_in"] = True
            if username == "admin":
                return redirect("/admin")
            return redirect("/")
        else:
            error = "Invalid credentials"
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/", methods=["GET", "POST"])
def index():
    if not session.get("logged_in"):
        return redirect("/login")
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT name FROM drinks")
    drinks_list = [row[0] for row in c.fetchall()]
    message = ""
    summary = None
    matching_names = []

    if request.method == "POST":
        unique_id = request.form.get("unique_id", "").zfill(4)  # Retain leading zeros
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        drink = request.form.get("drink", "")
        try:
            qty = int(request.form.get("quantity", "0").strip())
        except:
            qty = 0
        try:
            redeemed = int(request.form.get("redeemed", "0").strip())
        except:
            redeemed = 0

        tokens = qty // 9
        c.execute("SELECT SUM(tokens) - SUM(redeemed) FROM orders WHERE unique_id=?", (unique_id,))
        balance = c.fetchone()[0] or 0
        if redeemed > balance:
            message = f"❌ Not enough tokens. Current balance: {balance}"
        else:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("""
                INSERT INTO orders (unique_id, customer_name, quantity, tokens, redeemed, date, drink_type, phone)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (unique_id, name, qty, tokens, redeemed, now, drink, phone))
            conn.commit()
            message = "✅ Order submitted."

    # Check for summary and matching names if unique_id entered
    unique_id = request.args.get("unique_id", "")
    if unique_id:
        unique_id = unique_id.zfill(4)
        c.execute("""
            SELECT customer_name FROM orders WHERE unique_id=? GROUP BY customer_name
        """, (unique_id,))
        matching_names = [row[0] for row in c.fetchall()]

        c.execute("""
            SELECT SUM(quantity), SUM(tokens), SUM(redeemed) FROM orders WHERE unique_id=?
        """, (unique_id,))
        row = c.fetchone()
        if row and any(row):
            total_orders = row[0] or 0
            tokens_earned = row[1] or 0
            tokens_redeemed = row[2] or 0
            summary = {
                "orders": total_orders,
                "earned": tokens_earned,
                "redeemed": tokens_redeemed,
                "balance": tokens_earned - tokens_redeemed
            }

    conn.close()
    return render_template("index.html",
                           drinks=drinks_list,
                           message=message,
                           summary=summary,
                           unique_id=unique_id,
                           matching_names=matching_names)

if __name__ == "__main__":
    import os
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
