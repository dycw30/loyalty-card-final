from flask import Flask, render_template, request, redirect, session, url_for, send_file
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

def init_orders_db():
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
    # Default drinks
    c.execute("INSERT OR IGNORE INTO drinks (name) VALUES ('Latte'), ('Espresso'), ('Cappuccino'), ('Mocha')")
    conn.commit()
    conn.close()

def init_users_db():
    conn = sqlite3.connect(USERS_DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT
        )
    """)
    # Default admin user
    c.execute("INSERT OR IGNORE INTO users (username, password) VALUES ('admin', 'adminpass')")
    c.execute("INSERT OR IGNORE INTO users (username, password) VALUES ('barista1', 'coffee123')")
    conn.commit()
    conn.close()

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()

        conn = sqlite3.connect(USERS_DB)
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
        user = c.fetchone()
        conn.close()

        if user:
            session["username"] = username
            if username == "admin":
                return redirect("/admin")
            else:
                return redirect("/")
        else:
            error = "Invalid credentials"
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/", methods=["GET", "POST"])
def index():
    if "username" not in session or session["username"] == "admin":
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT name FROM drinks")
    drinks_list = [row[0] for row in c.fetchall()]
    totals = []
    message = ""

    if request.method == "POST":
        unique_id = request.form.get("unique_id", "").strip()
        quantity = int(request.form.get("quantity", "0").strip() or 0)
        redeemed = int(request.form.get("redeemed", "0").strip() or 0)
        drink_type = request.form.get("drink", "").strip()
        if drink_type == "N/A":
            drink_type = ""
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        tokens = quantity // 9
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        c.execute("SELECT SUM(tokens) - SUM(redeemed) FROM orders WHERE unique_id=?", (unique_id,))
        current_balance = c.fetchone()[0] or 0
        if redeemed > current_balance:
            message = f"❌ Not enough tokens to redeem. Current balance: {current_balance}"
        else:
            c.execute("""
                INSERT INTO orders (unique_id, customer_name, quantity, tokens, redeemed, date, drink_type, phone)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (unique_id, name, quantity, tokens, redeemed, date, drink_type, phone))
            conn.commit()
            message = "✅ Order submitted successfully."

    c.execute("""
        SELECT unique_id, MAX(customer_name), SUM(quantity), SUM(tokens), SUM(redeemed), MAX(phone)
        FROM orders GROUP BY unique_id
    """)
    totals = c.fetchall()
    conn.close()
    return render_template("index.html", totals=totals, drinks=drinks_list, message=message)

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if "username" not in session or session["username"] != "admin":
        return redirect(url_for("login"))

    conn_orders = sqlite3.connect(DB_NAME)
    conn_users = sqlite3.connect(USERS_DB)
    c_orders = conn_orders.cursor()
    c_users = conn_users.cursor()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "add_barista":
            user = request.form.get("new_barista", "").strip()
            pwd = request.form.get("new_password", "").strip()
            if user and pwd:
                c_users.execute("INSERT OR IGNORE INTO users (username, password) VALUES (?, ?)", (user, pwd))
                conn_users.commit()

        if action == "add_drink":
            drink = request.form.get("new_drink", "").strip()
            if drink:
                c_orders.execute("INSERT OR IGNORE INTO drinks (name) VALUES (?)", (drink,))
                conn_orders.commit()

        if "delete_user" in request.form:
            user = request.form.get("delete_user")
            if user != "admin":
                c_users.execute("DELETE FROM users WHERE username=?", (user,))
                conn_users.commit()

        if "delete_drink" in request.form:
            drink = request.form.get("delete_drink")
            c_orders.execute("DELETE FROM drinks WHERE name=?", (drink,))
            conn_orders.commit()

    c_users.execute("SELECT username FROM users")
    baristas = [row[0] for row in c_users.fetchall()]
    c_orders.execute("SELECT name FROM drinks")
    drinks = [row[0] for row in c_orders.fetchall()]

    conn_orders.close()
    conn_users.close()

    return render_template("admin.html", baristas=baristas, drinks=drinks)

@app.route("/export")
def export():
    if "username" not in session:
        return redirect(url_for("login"))
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("""
        SELECT unique_id AS 'Unique ID', MAX(customer_name) AS 'Customer Name', SUM(quantity) AS 'Total Orders',
               SUM(tokens) AS 'Tokens Earned', SUM(redeemed) AS 'Tokens Redeemed', MAX(phone) AS 'Phone'
        FROM orders GROUP BY unique_id
    """, conn)
    conn.close()
    file_name = "Bound Cafe Aggregated Export.xlsx"
    df.to_excel(file_name, index=False)
    return send_file(file_name, as_attachment=True)

@app.route("/pdf/<unique_id>")
def generate_pdf(unique_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        SELECT unique_id, MAX(customer_name), SUM(quantity), SUM(tokens), SUM(redeemed), MAX(phone)
        FROM orders WHERE unique_id=?
    """, (unique_id,))
    data = c.fetchone()
    conn.close()

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    p.drawString(100, 800, f"Customer Summary for ID: {data[0]}")
    p.drawString(100, 780, f"Name: {data[1]}")
    p.drawString(100, 760, f"Total Orders: {data[2]}")
    p.drawString(100, 740, f"Tokens Earned: {data[3]}")
    p.drawString(100, 720, f"Tokens Redeemed: {data[4]}")
    p.drawString(100, 700, f"Phone: {data[5]}")
    p.showPage()
    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"{unique_id}_summary.pdf")

@app.route("/qr/<unique_id>")
def generate_qr(unique_id):
    img = qrcode.make(f"Customer ID: {unique_id}")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return send_file(buffer, mimetype="image/png", as_attachment=True, download_name=f"{unique_id}_qr.png")

@app.route("/lookup")
def lookup():
    if "username" not in session:
        return redirect(url_for("login"))
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        SELECT unique_id, MAX(customer_name), SUM(quantity), SUM(tokens), SUM(redeemed), MAX(phone)
        FROM orders GROUP BY unique_id
    """)
    customers = c.fetchall()
    conn.close()
    return render_template("lookup.html", customers=customers)

if __name__ == "__main__":
    init_orders_db()
    init_users_db()
    app.run(host="0.0.0.0", port=5000)
