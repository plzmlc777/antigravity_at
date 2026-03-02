"""
Migration: Create ai_symbol_history table.
Stores AI symbol selection pipeline results for history tracking.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import engine
from sqlalchemy import text


def migrate():
    with engine.connect() as conn:
        # Check if table already exists
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'ai_symbol_history'
            )
        """))
        exists = result.scalar()

        if not exists:
            conn.execute(text("""
                CREATE TABLE ai_symbol_history (
                    id VARCHAR PRIMARY KEY,
                    session_id VARCHAR NOT NULL REFERENCES live_bot_sessions(id),
                    group_id VARCHAR,
                    action VARCHAR NOT NULL,
                    old_symbol VARCHAR NOT NULL,
                    old_symbol_name VARCHAR,
                    new_symbol VARCHAR,
                    new_symbol_name VARCHAR,
                    search_conditions TEXT,
                    evaluation_reason TEXT,
                    backtest_results JSONB,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """))
            conn.execute(text(
                "CREATE INDEX idx_ai_symbol_history_session ON ai_symbol_history(session_id)"
            ))
            conn.execute(text(
                "CREATE INDEX idx_ai_symbol_history_group ON ai_symbol_history(group_id)"
            ))
            conn.execute(text(
                "CREATE INDEX idx_ai_symbol_history_created ON ai_symbol_history(created_at)"
            ))
            print("Created table: ai_symbol_history")
        else:
            print("Skipped: ai_symbol_history (already exists)")

        conn.commit()
        print("Migration complete.")


if __name__ == "__main__":
    migrate()
