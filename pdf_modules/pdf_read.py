import sqlite3

def save_pdf_from_db(invoice_id, output_path):
    conn = sqlite3.connect("RMC_Sales.db")
    cursor = conn.cursor()
    cursor.execute("SELECT pdf_invoice FROM invoices WHERE invoice_id=?", (invoice_id,))
    result = cursor.fetchone()
    conn.close()
    print(result, result[0])
    if result and result[0]:
        with open(output_path, "wb") as f:
            f.write(result[0])
        print(f"PDF saved to {output_path}")
    else:
        print("No PDF data found for the specified invoice.")

# Save the PDF for the first invoice to a file
save_pdf_from_db("RMC / 24 - 25 / 202", "first_invoice_test.pdf")
