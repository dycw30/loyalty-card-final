from flask import Flask, render_template, request, redirect, session, url_for, send_file, jsonify
import sqlite3
from datetime import datetime
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
import qrcode
import io

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
            return redirect("/admin" if username == "admin" else "/")
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
    totals = []

    if request.method == "POST":
        unique_id = request.form.get("unique_id", "").zfill(4)
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
            message = f"❌ Not enough tokens to redeem. Current balance: {balance}"
        else:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("""
                INSERT INTO orders (unique_id, customer_name, quantity, tokens, redeemed, date, drink_type, phone)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (unique_id, name, qty, tokens, redeemed, now, drink, phone))
            conn.commit()
            message = "✅ Order submitted."

    c.execute("""
        SELECT unique_id, MAX(customer_name), SUM(quantity), SUM(tokens), SUM(redeemed), MAX(phone)
        FROM orders GROUP BY unique_id
    """)
    totals = c.fetchall()
    conn.close()

    return render_template("index.html", drinks=drinks_list, totals=totals, message=message)

@app.route("/lookup_matches", methods=["GET"])
def lookup_matches():
    unique_id = request.args.get("unique_id", "").zfill(4)
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT DISTINCT customer_name FROM orders WHERE unique_id=?", (unique_id,))
    names = [row[0] for row in c.fetchall()]
    c.execute("""
        SELECT SUM(quantity), SUM(tokens), SUM(redeemed)
        FROM orders WHERE unique_id=?
    """, (unique_id,))
    summary = c.fetchone()
    conn.close()

    return jsonify({
        "names": names,
        "summary": {
            "orders": summary[0] or 0,
            "tokens": summary[1] or 0,
            "redeemed": summary[2] or 0,
            "balance": (summary[1] or 0) - (summary[2] or 0)
        }
    })

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not session.get("logged_in") or session.get("username") != "admin":
        return redirect("/login")

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    if request.method == "POST":
        if "new_user" in request.form:
            new_user = request.form["new_user"].strip()
            new_pass = request.form["new_pass"].strip()
            conn_u = sqlite3.connect(USERS_DB)
            cu = conn_u.cursor()
            cu.execute("INSERT OR IGNORE INTO users (username, password) VALUES (?, ?)", (new_user, new_pass))
            conn_u.commit()
            conn_u.close()
        elif "new_drink" in request.form:
            new_drink = request.form["new_drink"].strip()
            c.execute("INSERT OR IGNORE INTO drinks (name) VALUES (?)", (new_drink,))
            conn.commit()

    conn_u = sqlite3.connect(USERS_DB)
    cu = conn_u.cursor()
    cu.execute("SELECT username FROM users")
    users = [row[0] for row in cu.fetchall()]
    conn_u.close()

    c.execute("SELECT name FROM drinks")
    drinks = [row[0] for row in c.fetchall()]
    conn.close()

    return render_template("admin.html", users=users, drinks=drinks)

@app.route("/delete_user/<username>")
def delete_user(username):
    if username != "admin":
        conn = sqlite3.connect(USERS_DB)
        c = conn.cursor()
        c.execute("DELETE FROM users WHERE username=?", (username,))
        conn.commit()
        conn.close()
    return redirect("/admin")

@app.route("/delete_drink/<drink>")
def delete_drink(drink):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM drinks WHERE name=?", (drink,))
    conn.commit()
    conn.close()
    return redirect("/admin")

@app.route("/lookup")
def lookup():
    if not session.get("logged_in"):
        return redirect("/login")
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("""
        SELECT unique_id AS 'Unique ID', MAX(customer_name) AS 'Customer Name', SUM(quantity) AS 'Total Orders',
               SUM(tokens) AS 'Tokens Earned', SUM(redeemed) AS 'Tokens Redeemed', MAX(phone) AS 'Phone'
        FROM orders GROUP BY unique_id
    """, conn)
    conn.close()
    return render_template("lookup.html", customers=df.to_records(index=False))

@app.route("/export")
def export():
    if not session.get("logged_in"):
        return redirect("/login")
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("""
        SELECT unique_id AS 'Unique ID', MAX(customer_name) AS 'Customer Name', SUM(quantity) AS 'Total Orders',
               SUM(tokens) AS 'Tokens Earned', SUM(redeemed) AS 'Tokens Redeemed', MAX(phone) AS 'Phone'
        FROM orders GROUP BY unique_id
    """, conn)
    conn.close()
    filename = "Bound_Cafe_Export.xlsx"
    df.to_excel(filename, index=False)
    return send_file(filename, as_attachment=True)

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
