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
    # Seed default drinks if none exist
    c.execute("SELECT COUNT(*) FROM drinks")
    if c.fetchone()[0] == 0:
        default_drinks = ["Mocha", "Latte", "Espresso", "Cappuccino"]
        c.executemany("INSERT INTO drinks (name) VALUES (?)", [(d,) for d in default_drinks])
    conn.commit()
    conn.close()

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        if username == "admin" and password == "adminpass":
            session["role"] = "admin"
            return redirect(url_for("admin"))
        elif username.startswith("barista") and password == "coffee123":
            session["role"] = "barista"
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
    if session.get("role") != "barista":
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT name FROM drinks ORDER BY name")
    drinks = [row[0] for row in c.fetchall()]
    conn.close()

    message = ""
    summary = None
    recent_orders = []

    if request.method == "POST":
        unique_id = request.form["unique_id"]
        drink = request.form.get("drink")
        quantity = int(request.form.get("quantity") or 0)
        redeemed = int(request.form.get("redeem") or 0)
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tokens = quantity // 9

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT COALESCE(SUM(tokens),0)-COALESCE(SUM(redeemed),0) FROM orders WHERE unique_id=?", (unique_id,))
        balance = c.fetchone()[0]

        if redeemed > balance:
            message = f"Cannot redeem {redeemed} tokens. Only {balance} available."
        else:
            c.execute("INSERT INTO orders (unique_id, drink_type, quantity, tokens, redeemed, date) VALUES (?, ?, ?, ?, ?, ?)",
                      (unique_id, drink, quantity, tokens, redeemed, date))
            conn.commit()
            message = "Order saved."

        # Summary for this ID
        c.execute("""
            SELECT
                COALESCE(SUM(quantity),0),
                COALESCE(SUM(tokens),0),
                COALESCE(SUM(redeemed),0)
            FROM orders WHERE unique_id=?
        """, (unique_id,))
        total_orders, tokens_earned, total_redeemed = c.fetchone()
        balance = tokens_earned - total_redeemed

        summary = {
            "unique_id": unique_id,
            "total_orders": total_orders,
            "tokens_earned": tokens_earned,
            "redeemed": total_redeemed,
            "balance": balance
        }

        # Recent orders
        c.execute("""
            SELECT date, drink_type, quantity, tokens, redeemed
            FROM orders
            WHERE unique_id=?
            ORDER BY date DESC
            LIMIT 5
        """, (unique_id,))
        recent_orders = [{"date": row[0], "drink_type": row[1], "quantity": row[2],
                          "tokens": row[3], "redeemed": row[4]} for row in c.fetchall()]
        conn.close()

    return render_template("index.html", drinks=drinks, message=message,
                           summary=summary, recent_orders=recent_orders)

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if session.get("role") != "admin":
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    if request.method == "POST":
        new_drink = request.form.get("new_drink")
        if new_drink:
            try:
                c.execute("INSERT INTO drinks (name) VALUES (?)", (new_drink,))
                conn.commit()
            except sqlite3.IntegrityError:
                pass
    c.execute("SELECT name FROM drinks ORDER BY name")
    drinks = [row[0] for row in c.fetchall()]
    conn.close()
    return render_template("admin.html", drinks=drinks)

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
