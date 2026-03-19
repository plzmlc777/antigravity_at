"""
Migration: Add position_snapshot column to live_bot_sessions table.
Stores current position state as JSON for reliable PM2 restart recovery.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import engine
from sqlalchemy import text


def migrate():
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'live_bot_sessions'
        """))
        existing = {row[0] for row in result}

        if 'position_snapshot' not in existing:
            conn.execute(text(
                "ALTER TABLE live_bot_sessions ADD COLUMN position_snapshot JSON"
            ))
            print("Added: position_snapshot (JSON) to live_bot_sessions")
        else:
            print("Already exists: position_snapshot")

        conn.commit()


if __name__ == "__main__":
    migrate()
