"""
Migration script to add is_disabled field to exchange_accounts table.
Run from backend directory: python migrate_account_disabled_field.py
"""
import os
import sys
from dotenv import load_dotenv

# Load environment
load_dotenv(".env")
load_dotenv("../.env")

# Database connection
import psycopg2

def migrate():
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_SERVER", "localhost"),
        database=os.getenv("POSTGRES_DB", "antigravity"),
        user=os.getenv("POSTGRES_USER", "admin"),
        password=os.getenv("POSTGRES_PASSWORD", "admin123")
    )

    cursor = conn.cursor()

    try:
        # Check if column exists
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'exchange_accounts' AND column_name = 'is_disabled'
        """)

        if cursor.fetchone():
            print("Column 'is_disabled' already exists. Skipping migration.")
            return

        # Add is_disabled column
        print("Adding 'is_disabled' column to exchange_accounts table...")
        cursor.execute("""
            ALTER TABLE exchange_accounts
            ADD COLUMN is_disabled BOOLEAN DEFAULT FALSE
        """)

        conn.commit()
        print("Migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        sys.exit(1)
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    migrate()
