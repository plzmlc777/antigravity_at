"""Migration: Add ai_optimize_params column to live_bot_sessions."""
import sys
sys.path.insert(0, '.')

from app.db.session import engine
from sqlalchemy import text


def migrate():
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'live_bot_sessions'
        """))
        existing = {row[0] for row in result}

        if 'ai_optimize_params' not in existing:
            conn.execute(text(
                "ALTER TABLE live_bot_sessions ADD COLUMN ai_optimize_params JSON"
            ))
            print("Added: ai_optimize_params")
        else:
            print("Already exists: ai_optimize_params")

        conn.commit()


if __name__ == "__main__":
    migrate()
