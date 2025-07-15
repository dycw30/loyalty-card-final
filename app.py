from flask import Flask, render_template, request, redirect, send_file, session, url_for
import sqlite3
from datetime import datetime
import os
import pandas as pd

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
    c.execute("""
        CREATE TABLE IF NOT EXISTS drinks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
    """)
    # Seed data
    c.execute("SELECT COUNT(*) FROM drinks")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO drinks (name) VALUES (?)", [("Mocha",), ("Latte",), ("Espresso",), ("Cappuccino",)])
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                      [("admin", "adminpass", "admin"), ("david", "coffee123", "barista")])
    conn.commit()
    conn.close()

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT role FROM users WHERE username=? AND password=?", (username, password))
        result = c.fetchone()
        conn.close()
        if result:
            session["username"] = username
            session["role"] = result[0]
            return redirect(url_for("admin" if result[0] == "admin" else "index"))
        else:
            return render_template("login.html", error="Invalid credentials")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/", methods=["GET", "POST"])
def index():
    if session.get("role") != "barista":
        return redirect(url_for("login"))

    message, summary, recent_orders = "", None, []
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT name FROM drinks ORDER BY name")
    drinks = [row[0] for row in c.fetchall()]

    if request.method == "POST":
        unique_id = request.form["unique_id"]
        drink = request.form.get("drink")
        quantity = int(request.form.get("quantity") or 0)
        redeemed = int(request.form.get("redeem") or 0)
        tokens = quantity // 9
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("SELECT COALESCE(SUM(tokens),0)-COALESCE(SUM(redeemed),0) FROM orders WHERE unique_id=?", (unique_id,))
        balance = c.fetchone()[0]

        if redeemed > balance:
            message = f"Cannot redeem {redeemed} tokens. Only {balance} available."
        else:
            c.execute("INSERT INTO orders (unique_id, drink_type, quantity, tokens, redeemed, date) VALUES (?, ?, ?, ?, ?, ?)",
                      (unique_id, drink, quantity, tokens, redeemed, date))
            conn.commit()
            message = "Order saved."

        # Refresh summary after submission
        c.execute("""
            SELECT COALESCE(SUM(quantity),0), COALESCE(SUM(tokens),0), COALESCE(SUM(redeemed),0)
            FROM orders WHERE unique_id=?
        """, (unique_id,))
        total_orders, tokens_earned, total_redeemed = c.fetchone()
        balance = tokens_earned - total_redeemed
        summary = {"unique_id": unique_id, "total_orders": total_orders, "tokens_earned": tokens_earned,
                   "redeemed": total_redeemed, "balance": balance}

        c.execute("""
            SELECT date, drink_type, quantity, tokens, redeemed
            FROM orders WHERE unique_id=?
            ORDER BY date DESC LIMIT 5
        """, (unique_id,))
        recent_orders = [{"date": row[0], "drink_type": row[1], "quantity": row[2], "tokens": row[3], "redeemed": row[4]}
                         for row in c.fetchall()]

    # Always show all summary table
    c.execute("""
        SELECT unique_id,
               COALESCE(SUM(quantity),0),
               COALESCE(SUM(tokens),0),
               COALESCE(SUM(redeemed),0),
               COALESCE(SUM(tokens),0) - COALESCE(SUM(redeemed),0) AS balance
        FROM orders
        GROUP BY unique_id
        ORDER BY unique_id
    """)
    all_summary = [{"unique_id": row[0], "total_orders": row[1], "tokens_earned": row[2],
                    "redeemed": row[3], "balance": row[4]} for row in c.fetchall()]
    conn.close()

    return render_template("index.html", drinks=drinks, message=message, summary=summary,
                           recent_orders=recent_orders, all_summary=all_summary)

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    if request.method == "POST":
        new_drink = request.form.get("new_drink")
        new_user = request.form.get("new_user")
        new_pass = request.form.get("new_pass")
        if new_drink:
            try: c.execute("INSERT INTO drinks (name) VALUES (?)", (new_drink,))
            except sqlite3.IntegrityError: pass
        if new_user and new_pass:
            try: c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, 'barista')", (new_user, new_pass))
            except sqlite3.IntegrityError: pass
        conn.commit()
    c.execute("SELECT name FROM drinks ORDER BY name")
    drinks = [row[0] for row in c.fetchall()]
    c.execute("SELECT username, role FROM users ORDER BY username")
    users = [{"username": row[0], "role": row[1]} for row in c.fetchall()]
    conn.close()
    return render_template("admin.html", drinks=drinks, users=users)

@app.route("/export")
def export():
    if not session.get("role"):
        return redirect(url_for("login"))
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM orders", conn)
    conn.close()
    if df.empty:
        return "No data to export"
    drink_pivot = df.pivot_table(index='unique_id', columns='drink_type', values='quantity', aggfunc='sum', fill_value=0)
    summary = df.groupby('unique_id').agg(
        total_orders=('quantity', 'sum'),
        tokens_earned=('tokens', 'sum'),
        redeemed=('redeemed', 'sum')
    ).reset_index()
    summary["balance"] = summary["tokens_earned"] - summary["redeemed"]
    combined = summary.merge(drink_pivot, on='unique_id', how='left').fillna(0)
    output_file = "Bound Cafe Aggregated Export.xlsx"
    combined.to_excel(output_file, index=False)
    return send_file(output_file, as_attachment=True)

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
