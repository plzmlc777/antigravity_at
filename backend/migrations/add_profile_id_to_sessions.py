"""
Migration: Add profile_id column to live_bot_sessions table.
Used for profile locking - prevents editing profiles that are in use by running sessions.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.db.session import engine
from sqlalchemy import text


def migrate():
    with engine.connect() as conn:
        # Check existing columns
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'live_bot_sessions'
        """))
        existing = {row[0] for row in result}

        if 'profile_id' not in existing:
            conn.execute(text(
                "ALTER TABLE live_bot_sessions ADD COLUMN profile_id VARCHAR"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_live_bot_sessions_profile_id ON live_bot_sessions (profile_id)"
            ))
            print("Added: profile_id column with index to live_bot_sessions")
        else:
            print("Column profile_id already exists, skipping.")

        conn.commit()


if __name__ == "__main__":
    migrate()
