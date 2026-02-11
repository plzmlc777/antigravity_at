"""
Migration: Add symbol_compare_settings column to strategy_profiles table
Date: 2025-02-11
Description: Symbol Compare 설정을 계정 레벨에서 프로필 레벨로 이동
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.db.session import engine


def migrate():
    """Add symbol_compare_settings column to strategy_profiles table"""
    with engine.connect() as conn:
        # Check if column already exists
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'strategy_profiles' AND column_name = 'symbol_compare_settings'
        """))

        if result.fetchone():
            print("Column 'symbol_compare_settings' already exists in strategy_profiles")
            return

        # Add the column
        conn.execute(text("""
            ALTER TABLE strategy_profiles
            ADD COLUMN symbol_compare_settings JSON NULL
        """))

        print("Added 'symbol_compare_settings' column to strategy_profiles table")

        conn.commit()
        print("Migration completed successfully!")


def rollback():
    """Remove symbol_compare_settings column from strategy_profiles table"""
    with engine.connect() as conn:
        # Check if column exists
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'strategy_profiles' AND column_name = 'symbol_compare_settings'
        """))

        if not result.fetchone():
            print("Column 'symbol_compare_settings' does not exist in strategy_profiles")
            return

        conn.execute(text("""
            ALTER TABLE strategy_profiles
            DROP COLUMN symbol_compare_settings
        """))

        print("Removed 'symbol_compare_settings' column from strategy_profiles table")

        conn.commit()
        print("Rollback completed successfully!")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--rollback', action='store_true', help='Rollback the migration')
    args = parser.parse_args()

    if args.rollback:
        rollback()
    else:
        migrate()
