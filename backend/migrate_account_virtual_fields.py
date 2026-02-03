"""
Migration: Add is_virtual and api_url columns to exchange_accounts table.
v0.9.9.37 -> v0.9.9.38

Run: python3 migrate_account_virtual_fields.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import engine
from sqlalchemy import text

def migrate():
    with engine.connect() as conn:
        # Check existing columns
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'exchange_accounts'
        """))
        existing = {row[0] for row in result}
        print(f"Existing columns: {sorted(existing)}")

        # Add is_virtual column (가상 계좌 여부)
        if 'is_virtual' not in existing:
            conn.execute(text("""
                ALTER TABLE exchange_accounts
                ADD COLUMN is_virtual BOOLEAN DEFAULT FALSE
            """))
            print("Added: is_virtual (BOOLEAN DEFAULT FALSE)")
        else:
            print("Skipped: is_virtual (already exists)")

        # Add api_url column (per-account API endpoint)
        if 'api_url' not in existing:
            conn.execute(text("""
                ALTER TABLE exchange_accounts
                ADD COLUMN api_url VARCHAR(255) NULL
            """))
            print("Added: api_url (VARCHAR(255) NULL)")
        else:
            print("Skipped: api_url (already exists)")

        conn.commit()
        print("\nMigration complete.")

if __name__ == "__main__":
    migrate()
