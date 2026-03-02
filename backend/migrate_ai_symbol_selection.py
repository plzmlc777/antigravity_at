"""
Migration: Add AI Symbol Selection columns to live_bot_sessions.
Adds: ai_symbol_mode, ai_search_conditions
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

        if 'ai_symbol_mode' not in existing:
            conn.execute(text(
                "ALTER TABLE live_bot_sessions ADD COLUMN ai_symbol_mode VARCHAR DEFAULT 'static'"
            ))
            print("Added: ai_symbol_mode")
        else:
            print("Skipped: ai_symbol_mode (already exists)")

        if 'ai_search_conditions' not in existing:
            conn.execute(text(
                "ALTER TABLE live_bot_sessions ADD COLUMN ai_search_conditions TEXT"
            ))
            print("Added: ai_search_conditions")
        else:
            print("Skipped: ai_search_conditions (already exists)")

        conn.commit()
        print("Migration complete.")


if __name__ == "__main__":
    migrate()
