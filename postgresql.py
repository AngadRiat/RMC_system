import psycopg2
from psycopg2.extras import DictCursor
from werkzeug.security import generate_password_hash

# Database connection parameters
DB_PARAMS = {
    "dbname": "rmc_sales",
    "user": "angad",
    "password": "0414182521",
    "host": "localhost",
    "port": "5432"  # Default is 5432
}
# Function to create a database connection and return the cursor
def get_db():
    conn = psycopg2.connect(**DB_PARAMS)
    return conn, conn.cursor()

# Function to create the tables
def create_tables():
    conn, cursor = get_db()
    
    # Create the users table
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        username TEXT PRIMARY KEY,
                        password TEXT NOT NULL,
                        name TEXT NOT NULL,
                        role TEXT NOT NULL
                    )''')

    hashed_password = generate_password_hash("0414182521")
    
    cursor.execute('INSERT INTO users (username, name, password, role) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING', 
                   ("angad", "Angad Riat", hashed_password, "admin"))
    
    cursor.execute('INSERT INTO users (username, name, password, role) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING',
                   ("prabin", "Prabin Saha", hashed_password, "viewer"))
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS buyer_info (
                    buyer_id SERIAL PRIMARY KEY,
                    buyer_name TEXT UNIQUE NOT NULL,
                    buyer_gst TEXT NOT NULL
                )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS buyer_addresses (
                    address_id SERIAL PRIMARY KEY,
                    buyer_id INTEGER NOT NULL,
                    address TEXT NOT NULL,
                    FOREIGN KEY (buyer_id) REFERENCES buyer_info (buyer_id)
                )''')

    # Create the invoices table
    cursor.execute('''CREATE TABLE IF NOT EXISTS invoices (
                    invoice_id TEXT PRIMARY KEY,
                    invoice_date TIMESTAMP NOT NULL,
                    buyer_id INTEGER,
                    address_id INTEGER,
                    po_details TEXT,
                    consignee_details TEXT NOT NULL,
                    dispatch TEXT,
                    total_price INT NOT NULL,
                    final_amount INT NOT NULL,
                    pdf_invoice BYTEA,
                    FOREIGN KEY (buyer_id) REFERENCES buyer_info (buyer_id),
                    FOREIGN KEY (address_id) REFERENCES buyer_addresses (address_id)
                )''')

    # Create the invoice_items table
    cursor.execute('''CREATE TABLE IF NOT EXISTS invoice_items (
                        item_id SERIAL PRIMARY KEY,
                        invoice_id TEXT,
                        description TEXT NOT NULL,
                        hsn_code TEXT NOT NULL,
                        quantity INTEGER NOT NULL,
                        rate INTEGER NOT NULL,
                        price INTEGER NOT NULL,
                        FOREIGN KEY (invoice_id) REFERENCES invoices (invoice_id)
                    )''')  

    # Commit the changes and close the connection
    conn.commit()
    conn.close()

# Main function
if __name__ == '__main__':
    try:
        create_tables()
        print("Database and tables created successfully!")
    except Exception as e:
        print(f"An error occurred: {str(e)}") 
        
# Connect to the PostgreSQL database
conn, cursor = get_db()

# Query data
cursor.execute("SELECT invoice_id, invoice_date, buyer_id, address_id, po_details, consignee_details, dispatch, total_price, final_amount FROM invoices")
rows = cursor.fetchall()

print("\nInvoice details\n")
for row in rows:
    print(row)
    
print("\nBuyer table details\n")
cursor.execute("SELECT * FROM buyer_info")
rows = cursor.fetchall()
for row in rows:
    print(row)
    
print("\nBuyer Addresses table details\n")
cursor.execute("SELECT * FROM buyer_addresses")
rows = cursor.fetchall()
for row in rows:
    print(row)
    
print("\nInvoice Item details\n")
cursor.execute("SELECT * FROM invoice_items")
rows = cursor.fetchall()
for row in rows:
    print(row)

print("\nUser details\n")
cursor.execute("SELECT * FROM users")
rows = cursor.fetchall()
for row in rows:
    print(row)

# Close the connection
cursor.close()
conn.close()
