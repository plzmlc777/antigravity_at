"""
Migration: Add is_paper and trade_metadata columns to live_trade_executions table.
v0.9.9.10 -> v0.9.9.11

Run: python3 migrate_trade_execution_columns.py
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
            WHERE table_name = 'live_trade_executions'
        """))
        existing = {row[0] for row in result}
        print(f"Existing columns: {sorted(existing)}")

        # Add is_paper column
        if 'is_paper' not in existing:
            conn.execute(text("""
                ALTER TABLE live_trade_executions
                ADD COLUMN is_paper BOOLEAN DEFAULT TRUE
            """))
            print("Added: is_paper (BOOLEAN DEFAULT TRUE)")
        else:
            print("Skipped: is_paper (already exists)")

        # Rename metadata -> trade_metadata if old name exists
        if 'metadata' in existing and 'trade_metadata' not in existing:
            conn.execute(text("""
                ALTER TABLE live_trade_executions
                RENAME COLUMN metadata TO trade_metadata
            """))
            print("Renamed: metadata -> trade_metadata")
        elif 'trade_metadata' not in existing:
            conn.execute(text("""
                ALTER TABLE live_trade_executions
                ADD COLUMN trade_metadata JSON
            """))
            print("Added: trade_metadata (JSON)")
        else:
            print("Skipped: trade_metadata (already exists)")

        conn.commit()
        print("\nMigration complete.")

if __name__ == "__main__":
    migrate()
