"""
Migration: Add account_id column to strategy_profiles table.
Enables profile-account binding for automatic exchange detection.
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
            WHERE table_name = 'strategy_profiles'
        """))
        existing = {row[0] for row in result}

        if 'account_id' not in existing:
            conn.execute(text("ALTER TABLE strategy_profiles ADD COLUMN account_id INTEGER"))
            print("Added: account_id to strategy_profiles")
        else:
            print("Column account_id already exists")

        conn.commit()
        print("Migration complete.")


if __name__ == "__main__":
    migrate()
