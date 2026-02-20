"""
Migration: Add futures-specific columns to live_bot_sessions and live_trade_executions.
- live_bot_sessions: leverage, margin_type, position_mode
- live_trade_executions: position_side

Safe to run multiple times (idempotent).
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.db.session import engine
from sqlalchemy import text


def migrate():
    with engine.connect() as conn:
        # ── live_bot_sessions ──
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'live_bot_sessions'
        """))
        existing = {row[0] for row in result}

        if 'leverage' not in existing:
            conn.execute(text("ALTER TABLE live_bot_sessions ADD COLUMN leverage INTEGER DEFAULT 1"))
            print("Added: live_bot_sessions.leverage")

        if 'margin_type' not in existing:
            conn.execute(text("ALTER TABLE live_bot_sessions ADD COLUMN margin_type VARCHAR(10) DEFAULT 'CROSSED'"))
            print("Added: live_bot_sessions.margin_type")

        if 'position_mode' not in existing:
            conn.execute(text("ALTER TABLE live_bot_sessions ADD COLUMN position_mode VARCHAR(10) DEFAULT 'ONE_WAY'"))
            print("Added: live_bot_sessions.position_mode")

        # ── live_trade_executions ──
        result2 = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'live_trade_executions'
        """))
        existing2 = {row[0] for row in result2}

        if 'position_side' not in existing2:
            conn.execute(text("ALTER TABLE live_trade_executions ADD COLUMN position_side VARCHAR(10) DEFAULT 'LONG'"))
            print("Added: live_trade_executions.position_side")

        conn.commit()
        print("Futures migration complete.")


if __name__ == "__main__":
    migrate()
