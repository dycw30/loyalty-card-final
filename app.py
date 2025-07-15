from flask import Flask, render_template, request, redirect, send_file, session, url_for
import sqlite3
from datetime import datetime
import os
import pandas as pd
import qrcode
from io import BytesIO

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
            customer_name TEXT,
            phone_number TEXT,
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
        customer_name = request.form.get("customer_name")
        phone_number = request.form.get("phone_number")
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
            c.execute("""
                INSERT INTO orders (unique_id, customer_name, phone_number, drink_type, quantity, tokens, redeemed, date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (unique_id, customer_name, phone_number, drink, quantity, tokens, redeemed, date))
            conn.commit()
            message = "Order saved."

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

    c.execute("""
        SELECT unique_id, COALESCE(MAX(customer_name),''), COALESCE(MAX(phone_number),''),
               COALESCE(SUM(quantity),0), COALESCE(SUM(tokens),0), COALESCE(SUM(redeemed),0),
               COALESCE(SUM(tokens),0) - COALESCE(SUM(redeemed),0) AS balance
        FROM orders
        GROUP BY unique_id ORDER BY unique_id
    """)
    all_summary = [{"unique_id": row[0], "customer_name": row[1], "phone_number": row[2],
                    "total_orders": row[3], "tokens_earned": row[4], "redeemed": row[5], "balance": row[6]} for row in c.fetchall()]
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
        action = request.form.get("action")
        if action == "add_drink":
            try: c.execute("INSERT INTO drinks (name) VALUES (?)", (request.form["new_drink"],))
            except sqlite3.IntegrityError: pass
        elif action == "edit_drink":
            c.execute("UPDATE drinks SET name=? WHERE name=?", (request.form["edit_drink_new"], request.form["edit_drink_old"]))
        elif action == "delete_drink":
            c.execute("DELETE FROM drinks WHERE name=?", (request.form["delete_drink"],))
        elif action == "add_user":
            try: c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, 'barista')",
                           (request.form["new_user"], request.form["new_pass"]))
            except sqlite3.IntegrityError: pass
        elif action == "edit_user":
            c.execute("UPDATE users SET password=? WHERE username=?", (request.form["new_pass"], request.form["edit_user"]))
        elif action == "delete_user":
            c.execute("DELETE FROM users WHERE username=?", (request.form["delete_user"],))
        conn.commit()
    c.execute("SELECT name FROM drinks ORDER BY name")
    drinks = [row[0] for row in c.fetchall()]
    c.execute("SELECT username, role FROM users ORDER BY username")
    users = [{"username": row[0], "role": row[1]} for row in c.fetchall()]
    conn.close()
    return render_template("admin.html", drinks=drinks, users=users)

@app.route("/customer")
def customer():
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    unique_id = request.args.get("unique_id")
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        SELECT COALESCE(SUM(quantity),0), COALESCE(SUM(tokens),0), COALESCE(SUM(redeemed),0)
        FROM orders WHERE unique_id=?
    """, (unique_id,))
    total_orders, tokens_earned, total_redeemed = c.fetchone()
    balance = tokens_earned - total_redeemed
    summary = {"unique_id": unique_id, "total_orders": total_orders,
               "tokens_earned": tokens_earned, "redeemed": total_redeemed, "balance": balance}

    c.execute("""
        SELECT date, drink_type, quantity, tokens, redeemed
        FROM orders WHERE unique_id=?
        ORDER BY date DESC
    """, (unique_id,))
    transactions = [{"date": row[0], "drink": row[1], "quantity": row[2], "tokens": row[3], "redeemed": row[4]}
                    for row in c.fetchall()]
    conn.close()
    return render_template("customer.html", unique_id=unique_id, summary=summary, transactions=transactions)

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
    summary = df.groupby(['unique_id','customer_name','phone_number']).agg(
        total_orders=('quantity','sum'), tokens_earned=('tokens','sum'), redeemed=('redeemed','sum')
    ).reset_index()
    summary["balance"] = summary["tokens_earned"] - summary["redeemed"]
    combined = summary.merge(drink_pivot, on='unique_id', how='left').fillna(0)
    output_file = "Bound Cafe Aggregated Export.xlsx"
    combined.to_excel(output_file, index=False)
    return send_file(output_file, as_attachment=True)

@app.route("/qr")
def qr():
    url = "https://loyalty-card-app-v2.onrender.com"
    img = qrcode.make(url)
    buf = BytesIO()
    img.save(buf)
    buf.seek(0)
    return send_file(buf, mimetype='image/png', download_name='CafeQR.png', as_attachment=False)

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
