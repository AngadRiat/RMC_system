import psycopg2
from psycopg2.extras import DictCursor
from werkzeug.security import generate_password_hash

# Database connection parameters
DB_PARAMS = {
    "dbname": "rmc_sales_n53i",
    "user": "angadr",
    "password": "J8hmHOaf84rCOCz7n3MvLjPTTUjp81Ps",
    "host": "dpg-cv9hi28fnakc739q7h50-a.singapore-postgres.render.com",
    "port": "5432",
    "sslmode": "require"  # Required for external connections
}

# Function to connect to the database
def get_db():
    conn = psycopg2.connect(**DB_PARAMS)
    return conn, conn.cursor()

# Function to reset (drop and create) tables
def reset_database():
    conn, cursor = get_db()

    try:
        # Drop tables if they exist
        cursor.execute("""
            DROP TABLE IF EXISTS 
                buyer_addresses, 
                buyer_info, 
                consignee_addresses, 
                invoice_items, 
                invoices, 
                users CASCADE
        """)
        
        # Create new tables as per updated schema
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL
            )
        """)

        hashed_password = generate_password_hash("0414182521")

        cursor.execute("""
            INSERT INTO users (username, name, password, role) 
            VALUES 
                ('angad', 'Angad Riat', %s, 'admin'),
                ('prabin', 'Prabin Saha', %s, 'viewer')
            ON CONFLICT (username) DO NOTHING
        """, (hashed_password, hashed_password))

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS buyer_info (
                buyer_id SERIAL PRIMARY KEY,
                buyer_name TEXT UNIQUE NOT NULL,
                buyer_gst TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS buyer_addresses (
                address_id SERIAL PRIMARY KEY,
                buyer_id INTEGER NOT NULL,
                address TEXT NOT NULL,
                FOREIGN KEY (buyer_id) REFERENCES buyer_info (buyer_id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS consignee_addresses (
                consignee_id SERIAL PRIMARY KEY,
                buyer_id INTEGER NOT NULL,
                consignee_address TEXT NOT NULL,
                FOREIGN KEY (buyer_id) REFERENCES buyer_info (buyer_id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                invoice_id TEXT PRIMARY KEY,
                invoice_date TIMESTAMP NOT NULL,
                buyer_id INTEGER,
                address_id INTEGER,
                consignee_id INTEGER,
                po_details TEXT,
                dispatch TEXT,
                total_price INTEGER NOT NULL,
                final_amount INTEGER NOT NULL,
                pdf_invoice BYTEA,
                FOREIGN KEY (buyer_id) REFERENCES buyer_info (buyer_id) ON DELETE CASCADE,
                FOREIGN KEY (address_id) REFERENCES buyer_addresses (address_id) ON DELETE CASCADE,
                FOREIGN KEY (consignee_id) REFERENCES consignee_addresses (consignee_id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invoice_items (
                item_id SERIAL PRIMARY KEY,
                invoice_id TEXT,
                description TEXT NOT NULL,
                hsn_code TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                rate INTEGER NOT NULL,
                price INTEGER NOT NULL,
                FOREIGN KEY (invoice_id) REFERENCES invoices (invoice_id) ON DELETE CASCADE
            )
        """)

        conn.commit()
        print("✅ Database reset and tables created successfully!")

    except Exception as e:
        print(f"❌ Error: {str(e)}")
    
    finally:
        conn.close()

# Run the script
if __name__ == '__main__':
    reset_database()
