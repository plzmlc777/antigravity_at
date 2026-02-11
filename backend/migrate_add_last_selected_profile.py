#!/usr/bin/env python3
"""
Migration: Add last_selected_profile_id column to exchange_accounts table

Usage:
    python migrate_add_last_selected_profile.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from app.db.session import engine


def migrate():
    """Add last_selected_profile_id column to exchange_accounts if not exists"""
    with engine.connect() as conn:
        # Check if column exists
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'exchange_accounts'
            AND column_name = 'last_selected_profile_id'
        """))

        existing = list(result)

        if not existing:
            print("Adding last_selected_profile_id column to exchange_accounts...")
            conn.execute(text("""
                ALTER TABLE exchange_accounts
                ADD COLUMN last_selected_profile_id VARCHAR(255) NULL
            """))
            conn.commit()
            print("✓ Column added successfully")
        else:
            print("✓ Column already exists, skipping")


if __name__ == "__main__":
    print("=== Migration: Add last_selected_profile_id ===")
    migrate()
    print("Done.")
