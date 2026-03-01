"""
Migration: Create ai_trading_profiles and ai_trading_decisions tables
Purpose: AI-driven autonomous trading with dynamic stock/parameter selection
"""
from app.db.session import engine
from sqlalchemy import text


def migrate():
    with engine.connect() as conn:
        # Check existing tables
        result = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('ai_trading_profiles', 'ai_trading_decisions')
        """))
        existing = {row[0] for row in result}

        # ── Table 1: ai_trading_profiles ──
        if 'ai_trading_profiles' not in existing:
            conn.execute(text("""
                CREATE TABLE ai_trading_profiles (
                    id VARCHAR(255) PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    strategy_name VARCHAR(255) NOT NULL,
                    stock_source_mode VARCHAR(50) DEFAULT 'AI_AUTO_SEARCH',
                    fixed_symbols JSONB,
                    candidate_symbols JSONB,
                    search_conditions TEXT,
                    param_ranges JSONB,
                    fixed_params JSONB,
                    backtest_days INTEGER DEFAULT 30,
                    backtest_interval VARCHAR(10) DEFAULT '1m',
                    optimization_top_n INTEGER DEFAULT 5,
                    max_optimization_combos INTEGER DEFAULT 500,
                    approval_mode VARCHAR(20) DEFAULT 'AUTO',
                    account_id INTEGER,
                    initial_capital FLOAT DEFAULT 10000000,
                    is_paper BOOLEAN DEFAULT TRUE,
                    max_consecutive_losses INTEGER DEFAULT 5,
                    cooldown_minutes INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    is_running BOOLEAN DEFAULT FALSE,
                    current_session_id VARCHAR(255),
                    current_symbol VARCHAR(50),
                    cycles_completed INTEGER DEFAULT 0,
                    consecutive_losses INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_decision_at TIMESTAMP
                )
            """))
            print("Created: ai_trading_profiles table")

            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_ai_trading_profiles_user_id
                ON ai_trading_profiles (user_id)
            """))
            print("Created: index on ai_trading_profiles.user_id")
        else:
            print("Table ai_trading_profiles already exists, skipping.")

        # ── Table 2: ai_trading_decisions ──
        if 'ai_trading_decisions' not in existing:
            conn.execute(text("""
                CREATE TABLE ai_trading_decisions (
                    id VARCHAR(255) PRIMARY KEY,
                    profile_id VARCHAR(255) NOT NULL REFERENCES ai_trading_profiles(id),
                    trigger_type VARCHAR(50) DEFAULT 'initial_start',
                    previous_session_id VARCHAR(255),
                    previous_symbol VARCHAR(50),
                    previous_cycle_pnl FLOAT,
                    stock_candidates JSONB,
                    stock_selection_model VARCHAR(100),
                    stock_selection_duration_ms INTEGER,
                    optimization_results JSONB,
                    optimization_duration_ms INTEGER,
                    final_decision_model VARCHAR(100),
                    final_decision_duration_ms INTEGER,
                    chosen_symbol VARCHAR(50),
                    chosen_symbol_name VARCHAR(255),
                    chosen_params JSONB,
                    chosen_score FLOAT,
                    chosen_reasoning TEXT,
                    new_session_id VARCHAR(255),
                    status VARCHAR(50) DEFAULT 'PENDING',
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                )
            """))
            print("Created: ai_trading_decisions table")

            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_ai_trading_decisions_profile_id
                ON ai_trading_decisions (profile_id)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_ai_trading_decisions_created_at
                ON ai_trading_decisions (created_at)
            """))
            print("Created: indexes on ai_trading_decisions")
        else:
            print("Table ai_trading_decisions already exists, skipping.")

        # ── Add ai_profile_id to live_bot_sessions ──
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'live_bot_sessions' AND column_name = 'ai_profile_id'
        """))
        if not result.fetchone():
            conn.execute(text("""
                ALTER TABLE live_bot_sessions ADD COLUMN ai_profile_id VARCHAR(255)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_live_bot_sessions_ai_profile_id
                ON live_bot_sessions (ai_profile_id)
            """))
            print("Added: ai_profile_id column to live_bot_sessions")
        else:
            print("Column ai_profile_id already exists in live_bot_sessions, skipping.")

        conn.commit()
        print("AI Trading migration completed successfully!")


if __name__ == "__main__":
    migrate()
