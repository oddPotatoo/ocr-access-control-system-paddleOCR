import psycopg2
from datetime import datetime

# PostgreSQL connection setup
DB_PARAMS = {
    "dbname": "non_resident_logs",  # Replace with your new database name
    "user": "postgres",  # Change if using a different username
    "password": "meowthiebowingski",  # Replace with your actual password
    "host": "localhost",
    "port": "5432"
}

def connect_db():
    """Establish connection to PostgreSQL."""
    return psycopg2.connect(**DB_PARAMS)

def insert_vehicle_entry(full_name, id_type, id_number, qr_code):
    """Insert vehicle entry into the database."""
    conn = connect_db()
    cursor = conn.cursor()

    # Insert into the single table
    cursor.execute("""
        INSERT INTO "NonResidentLogs" (full_name, id_type, id_number, qr_code, entry_time)
        VALUES (%s, %s, %s, %s, %s) RETURNING id;
    """, (full_name, id_type, id_number, qr_code, datetime.now()))
    
    entry_id = cursor.fetchone()[0]
    conn.commit()
    
    cursor.close()
    conn.close()
    return entry_id