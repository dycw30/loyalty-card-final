from flask import Flask, render_template, request, redirect, url_for, session, send_file
import sqlite3
import pandas as pd
from datetime import datetime
import io

app = Flask(__name__)
app.secret_key = 'your_secret_key'

DB_FILE = 'orders.db'

# --- Helper to get matching customers by last 4 digits ---
def get_customers_by_unique_id(unique_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT DISTINCT customer_name FROM orders WHERE unique_id = ?", (unique_id,))
    names = [row[0] for row in c.fetchall()]
    conn.close()
    return names

# --- Home Route (Dashboard + Order Input) ---
@app.route('/', methods=['GET', 'POST'])
def index():
    message = ''
    customer_list = []

    if request.method == 'POST':
        unique_id = request.form['unique_id'].strip()
        customer_name = request.form.get('customer_name') or request.form.get('custom_name', '').strip()
        quantity = int(request.form.get('quantity', 0))
        drink_type = request.form.get('drink_type') or 'N/A'
        phone = request.form.get('phone', '').strip()

        tokens = quantity // 10
        date = datetime.now().strftime('%Y-%m-%d')

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()

        # Insert into DB
        c.execute("""INSERT INTO orders (unique_id, customer_name, quantity, tokens, redeemed, date, drink_type, phone)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                  (unique_id, customer_name, quantity, tokens, 0, date, drink_type, phone))
        conn.commit()

        # Get updated summary
        c.execute("""
            SELECT customer_name, unique_id,
                SUM(quantity) as total_orders,
                SUM(tokens) as tokens_earned,
                SUM(redeemed) as tokens_redeemed
            FROM orders
            WHERE unique_id = ?
            GROUP BY customer_name, unique_id
        """, (unique_id,))
        customer_list = c.fetchall()
        conn.close()

        message = 'Order recorded successfully!'

    return render_template('index.html', message=message, customers=customer_list)

# --- Lookup AJAX Endpoint ---
@app.route('/lookup', methods=['POST'])
def lookup():
    unique_id = request.form['unique_id']
    names = get_customers_by_unique_id(unique_id)
    return {'names': names}

# --- Export Route ---
@app.route('/export')
def export():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM orders", conn)
    conn.close()

    if df.empty:
        return "No data to export."

    # Pivot for drinks
    pivot = df.pivot_table(index=['customer_name', 'unique_id'], columns='drink_type', values='quantity', aggfunc='sum', fill_value=0)
    summary = df.groupby(['customer_name', 'unique_id']).agg({
        'quantity': 'sum',
        'tokens': 'sum',
        'redeemed': 'sum'
    }).rename(columns={
        'quantity': 'Total Orders',
        'tokens': 'Token Earned',
        'redeemed': 'Token Redeemed'
    }).reset_index()

    result = pd.merge(summary, pivot.reset_index(), on=['customer_name', 'unique_id'], how='left')
    result.insert(2, "Today's Order", '')  # Empty column
    result = result[['customer_name', 'unique_id', "Today's Order", 'Total Orders', 'Token Earned', 'Token Redeemed'] + list(pivot.columns)]
    result.rename(columns={'customer_name': 'Customer Name', 'unique_id': 'Unique ID'}, inplace=True)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        result.to_excel(writer, index=False, sheet_name='Loyalty Data')

    output.seek(0)
    return send_file(output, download_name="Bound Cafe Aggregated Export.xlsx", as_attachment=True)

# --- Init DB if needed ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
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
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    app.run(debug=False)
