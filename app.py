@app.route("/export")
def export():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # get main summary totals
    df = pd.read_sql_query("""
        SELECT unique_id,
               SUM(quantity) AS total_orders,
               SUM(quantity) / 9 AS total_tokens,
               SUM(redeemed) AS total_redeemed,
               (SUM(quantity) / 9) - SUM(redeemed) AS balance
        FROM orders
        GROUP BY unique_id
    """, conn)

    # get drink breakdown by customer
    drink_df = pd.read_sql_query("""
        SELECT unique_id, drink_type, SUM(quantity) AS qty
        FROM orders
        WHERE drink_type IS NOT NULL
        GROUP BY unique_id, drink_type
    """, conn)

    # pivot to have drink types as columns
    if not drink_df.empty:
        drink_pivot = drink_df.pivot(index="unique_id", columns="drink_type", values="qty").fillna(0).astype(int)
    else:
        drink_pivot = pd.DataFrame()

    # merge into main summary
    if not drink_pivot.empty:
        df = df.set_index("unique_id").join(drink_pivot).reset_index()

    conn.close()

    if df.empty:
        return "No data to export"

    wb = load_workbook("Bound CRM Test 3.xlsm", keep_vba=True)
    ws = wb["Sheet1"]

    # write headers
    headers = ["Unique ID", "Total Orders", "Tokens Earned", "Redeemed", "Balance"]
    drink_headers = list(drink_pivot.columns) if not drink_pivot.empty else []
    for idx, header in enumerate(headers + drink_headers, start=1):
        ws.cell(row=1, column=idx, value=header)

    # write data
    start_row = 2
    for i, row in df.iterrows():
        ws.cell(row=start_row + i, column=1, value=row["unique_id"])
        ws.cell(row=start_row + i, column=2, value=int(row["total_orders"]))
        ws.cell(row=start_row + i, column=3, value=int(row["total_tokens"]))
        ws.cell(row=start_row + i, column=4, value=int(row["total_redeemed"]))
        ws.cell(row=start_row + i, column=5, value=int(row["balance"]))

        for j, drink in enumerate(drink_headers, start=6):
            ws.cell(row=start_row + i, column=j, value=int(row.get(drink, 0)))

    wb.save("Bound Cafe Aggregated Export.xlsm")
    return send_file("Bound Cafe Aggregated Export.xlsm", as_attachment=True)
