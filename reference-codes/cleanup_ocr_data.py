import psycopg2
from datetime import datetime, timedelta

# Retention period in days
RETENTION_DAYS = 60

def delete_old_records():
    """Delete records older than 60 days from the NonResidentLogs table."""
    conn = psycopg2.connect(
        dbname="non_resident_logs",
        user="postgres",
        password="meowthiebowingski",
        host="localhost",
        port="5432"
    )
    cursor = conn.cursor()
    
    # Get current PH time (assuming server is already UTC+8)
    now_ph = datetime.now()
    
    # Calculate cutoff date (60 days ago in PH time)
    cutoff_ph = now_ph - timedelta(days=RETENTION_DAYS)
    
    # Delete records older than 60 days
    query = """
        DELETE FROM "NonResidentLogs"
        WHERE entry_time < %s;  -- Use 'entry_time' as the timestamp column
    """
    
    try:
        cursor.execute(query, (cutoff_ph,))
        conn.commit()
        print(f"Deleted {cursor.rowcount} records older than {cutoff_ph.strftime('%Y-%m-%d %H:%M:%S (UTC+8)')}")
    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    delete_old_records()