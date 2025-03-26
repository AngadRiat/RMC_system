import psycopg2

DB_PARAMS = {
    "dbname": "rmc_sales_n53i",
    "user": "angadr",
    "password": "J8hmHOaf84rCOCz7n3MvLjPTTUjp81Ps",
    "host": "dpg-cv9hi28fnakc739q7h50-a.singapore-postgres.render.com",
    "port": "5432",
    "sslmode": "require"
}

def get_db_stats():
    try:
        conn = psycopg2.connect(**DB_PARAMS)
        cursor = conn.cursor()

        # Get database size
        cursor.execute("SELECT pg_size_pretty(pg_database_size(current_database()));")
        db_size = cursor.fetchone()[0]

        # Get table sizes
        cursor.execute("""
            SELECT relname AS table_name, pg_size_pretty(pg_relation_size(relid)) 
            FROM pg_catalog.pg_statio_user_tables 
            ORDER BY pg_relation_size(relid) DESC;
        """)
        table_sizes = cursor.fetchall()

        print(f"📊 Database Size: {db_size}\n")

        print("📂 Table Sizes:")
        for table, size in table_sizes:
            print(f"   - {table}: {size}")

        # Get total PDF storage size
        cursor.execute("SELECT pg_size_pretty(SUM(pg_column_size(pdf_invoice)::bigint)) FROM invoices WHERE pdf_invoice IS NOT NULL;")
        total_pdf_size = cursor.fetchone()[0]

        # Get largest PDF file
        cursor.execute("""
            SELECT invoice_id, pg_size_pretty(pg_column_size(pdf_invoice)::bigint) AS size 
            FROM invoices 
            WHERE pdf_invoice IS NOT NULL 
            ORDER BY pg_column_size(pdf_invoice) DESC 
            LIMIT 1;
        """)
        largest_pdf = cursor.fetchone()

        # Get all PDFs with sizes
        cursor.execute("""
            SELECT invoice_id, pg_size_pretty(pg_column_size(pdf_invoice)::bigint) AS size 
            FROM invoices 
            WHERE pdf_invoice IS NOT NULL 
            ORDER BY invoice_id;
        """)
        pdf_sizes = cursor.fetchall()

        print(f"\n📄 Stored PDFs: Total Size: {total_pdf_size}")
        print(f"📌 Largest PDF: Invoice {largest_pdf[0]} - {largest_pdf[1]}\n")

        print("📜 All PDFs:")
        for invoice_id, size in pdf_sizes:
            print(f"   - Invoice {invoice_id}: {size}")

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    get_db_stats()