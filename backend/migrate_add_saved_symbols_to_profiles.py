"""
Migration: Add saved_symbols column to strategy_profiles table.
Target Asset 목록을 프로필 단위로 저장하기 위한 마이그레이션.
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

        if 'saved_symbols' not in existing:
            conn.execute(text("ALTER TABLE strategy_profiles ADD COLUMN saved_symbols JSONB"))
            print("Added: saved_symbols to strategy_profiles")
        else:
            print("Column saved_symbols already exists")

        conn.commit()
        print("Migration complete.")


if __name__ == "__main__":
    migrate()
