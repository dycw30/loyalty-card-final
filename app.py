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
        CREATE TABLE IF NOT EXISTS baristas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS drinks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
    """)
    # default admin and drinks
    c.execute("INSERT OR IGNORE INTO baristas (username, password) VALUES ('admin', 'coffee123')")
    c.execute("INSERT OR IGNORE INTO drinks (name) VALUES ('Latte'), ('Espresso'), ('Cappuccino'), ('Mocha')")
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
            session["username"] = username
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
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT name FROM drinks")
    drinks_list = [row[0] for row in c.fetchall()]
    totals = []
    message = ""

    if request.method == "POST":
        unique_id = request.form.get("unique_id", "").strip()
        try:
            quantity = int(request.form.get("quantity", "0").strip() or 0)
        except:
            quantity = 0
        try:
            redeemed = int(request.form.get("redeemed", "0").strip() or 0)
        except:
            redeemed = 0
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

@app.route("/export")
def export():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("""
        SELECT unique_id AS 'Unique ID', MAX(customer_name) AS 'Customer Name', SUM(quantity) AS 'Total Orders',
               SUM(tokens) AS 'Tokens Earned', SUM(redeemed) AS 'Tokens Redeemed', MAX(phone) AS 'Phone'
        FROM orders
        GROUP BY unique_id
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

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not session.get("logged_in") or session.get("username") != "admin":
        return redirect(url_for("login"))
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    if request.method == "POST":
        if "new_barista" in request.form:
            user = request.form["new_barista"].strip()
            pwd = request.form["new_password"].strip()
            c.execute("INSERT OR IGNORE INTO baristas (username, password) VALUES (?, ?)", (user, pwd))
        if "new_drink" in request.form:
            drink = request.form["new_drink"].strip()
            c.execute("INSERT OR IGNORE INTO drinks (name) VALUES (?)", (drink,))
        conn.commit()
    c.execute("SELECT username FROM baristas")
    baristas = [row[0] for row in c.fetchall()]
    c.execute("SELECT name FROM drinks")
    drinks = [row[0] for row in c.fetchall()]
    conn.close()
    return render_template("admin.html", baristas=baristas, drinks=drinks)

@app.route("/lookup")
def lookup():
    if not session.get("logged_in"):
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
    init_db()
    app.run(host="0.0.0.0", port=5000)
