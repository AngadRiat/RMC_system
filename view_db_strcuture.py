import psycopg2
from psycopg2.extras import DictCursor

# Database connection parameters
DB_PARAMS = {
    "dbname": "rmc_sales_n53i",
    "user": "angadr",
    "password": "J8hmHOaf84rCOCz7n3MvLjPTTUjp81Ps",
    "host": "dpg-cv9hi28fnakc739q7h50-a.singapore-postgres.render.com",
    "port": "5432",
    "sslmode": "require"  # Required for external connections
}

def get_db():
    """Establish a database connection and return connection and cursor."""
    conn = psycopg2.connect(**DB_PARAMS)
    return conn, conn.cursor(cursor_factory=DictCursor)

def view_db_structure():
    """Fetches and prints the structure of all tables in the database."""
    conn, cursor = get_db()
    
    try:
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        """)
        tables = cursor.fetchall()
        
        print("\nDatabase Structure:")
        for table in tables:
            table_name = table["table_name"]
            print(f"\nTable: {table_name}")
            
            cursor.execute(f"""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns 
                WHERE table_name = %s
            """, (table_name,))
            
            columns = cursor.fetchall()
            for col in columns:
                print(f"  - {col['column_name']} ({col['data_type']}), Nullable: {col['is_nullable']}, Default: {col['column_default']}")
    
    except Exception as e:
        print(f"❌ Error: {str(e)}")
    
    finally:
        conn.close()

# Run the script
if __name__ == '__main__':
    view_db_structure()
