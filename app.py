@app.route("/export")
def export():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # aggregate main totals
    df = pd.read_sql_query("""
        SELECT unique_id,
               SUM(quantity) AS total_orders,
               SUM(quantity) / 9 AS total_tokens,
               SUM(redeemed) AS total_redeemed,
               (SUM(quantity) / 9) - SUM(redeemed) AS balance
        FROM orders
        GROUP BY unique_id
    """, conn)

    # get top drink for each Unique ID
    c.execute("""
        SELECT unique_id, drink_type, SUM(quantity) as qty
        FROM orders
        WHERE drink_type IS NOT NULL
        GROUP BY unique_id, drink_type
        ORDER BY unique_id, qty DESC
    """)
    rows = c.fetchall()

    # build a top drink mapping
    top_drink_map = {}
    for uid, drink, qty in rows:
        if uid not in top_drink_map:
            top_drink_map[uid] = drink

    conn.close()

    if df.empty:
        return "No data to export"

    # load your Bound CRM Excel template
    wb = load_workbook("Bound CRM Test 3.xlsm", keep_vba=True)
    ws = wb["Sheet1"]

    start_row = 2
    for i, row in df.iterrows():
        uid = row["unique_id"]
        ws.cell(row=start_row + i, column=1, value=uid)
        ws.cell(row=start_row + i, column=3, value=int(row["total_orders"]))
        ws.cell(row=start_row + i, column=4, value=int(row["total_tokens"]))
        ws.cell(row=start_row + i, column=5, value=int(row["total_redeemed"]))
        ws.cell(row=start_row + i, column=6, value=int(row["balance"]))
        ws.cell(row=start_row + i, column=7, value=top_drink_map.get(uid, "N/A"))

    wb.save("Bound Cafe Aggregated Export.xlsm")
    return send_file("Bound Cafe Aggregated Export.xlsm", as_attachment=True)
