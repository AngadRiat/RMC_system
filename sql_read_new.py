import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

# Database name
DATABASE = 'RMC_Sales_new.db'

# Function to create a database connection and return the cursor
def get_db():
    conn = sqlite3.connect(DATABASE)
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
    
    cursor.execute('INSERT INTO users (username, name, password, role) VALUES (?, ?, ?, ?)', 
                ("angad", "Angad Riat", hashed_password, "admin"))
    
    cursor.execute('INSERT INTO users (username, name, password, role) VALUES (?, ?, ?, ?)',
                   ("prabin", "Prabin Saha", hashed_password, "viewer"))
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS buyer_info (
                    buyer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    buyer_name TEXT UNIQUE NOT NULL,
                    buyer_gst TEXT NOT NULL
                )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS buyer_addresses (
                    address_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    buyer_id INTEGER NOT NULL,
                    address TEXT NOT NULL,
                    FOREIGN KEY (buyer_id) REFERENCES buyer_info (buyer_id)
                )''')

    # Create the invoices table
    cursor.execute('''CREATE TABLE IF NOT EXISTS invoices (
                    invoice_id TEXT PRIMARY KEY,
                    invoice_date TEXT NOT NULL,
                    buyer_id INTEGER,
                    address_id INTEGER,
                    po_details TEXT,
                    consignee_details TEXT NOT NULL,
                    dispatch TEXT,
                    total_price INT NOT NULL,
                    final_amount INT NOT NULL,
                    pdf_invoice BLOB,
                    FOREIGN KEY (buyer_id) REFERENCES buyer_info (buyer_id),
                    FOREIGN KEY (address_id) REFERENCES buyer_addresses (address_id)
                )''')

    # Create the invoice_items table
    cursor.execute('''CREATE TABLE IF NOT EXISTS invoice_items (
                        item_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        

# Connect to the SQLite database
connection = sqlite3.connect('RMC_Sales_new.db')
cursor = connection.cursor()

#cursor.execute("ALTER TABLE invoices ADD COLUMN pdf_invoice BLOB;")
#cursor.execute("DELETE FROM invoices;")
#cursor.execute("DELETE FROM invoice_items;")

# Query data
cursor.execute("SELECT invoice_id, invoice_date, buyer_id, address_id, po_details, consignee_details, dispatch, total_price, final_amount FROM invoices")
rows = cursor.fetchall()

print("")
print("Invoice details")
print("")

# Loop through and print each row
for row in rows:
    print(row)
    
print("\n")

print("Buyer table details")
print("")
cursor.execute("SELECT * FROM buyer_info")
rows = cursor.fetchall()

# Loop through and print each row
for row in rows:
    print(row)
    
    print("\n")

print("Buyer Addresses table details")
print("")
cursor.execute("SELECT * FROM buyer_addresses")
rows = cursor.fetchall()

# Loop through and print each row
for row in rows:
    print(row)
    
print("\n")

print("Invoice Item details")
print("")
cursor.execute("SELECT * FROM invoice_items")
rows = cursor.fetchall()

# Loop through and print each row
for row in rows:
    print(row)

print()

print("User details")
print("")
cursor.execute("SELECT * FROM users")
rows = cursor.fetchall()

# Loop through and print each row
for row in rows:
    print(row)

print() 
# Close the connection
connection.close()
