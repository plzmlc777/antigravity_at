"""
Migration script to create live_ai_evaluations table.
Run: python migrate_ai_evaluation_table.py
"""
from sqlalchemy import create_engine, text
from app.core.config import settings

def main():
    print(f"Migrating schema on: {settings.POSTGRES_SERVER}")

    # Build connection string
    port = getattr(settings, 'POSTGRES_PORT', "5432")
    db_uri = f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_SERVER}:{port}/{settings.POSTGRES_DB}"

    engine = create_engine(db_uri)

    with engine.connect() as conn:
        # Create live_ai_evaluations table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS live_ai_evaluations (
                id VARCHAR PRIMARY KEY,
                session_id VARCHAR NOT NULL REFERENCES live_bot_sessions(id),
                symbol VARCHAR NOT NULL,

                -- Trigger Info
                evaluation_type VARCHAR DEFAULT 'MANUAL',
                trigger_cycle_count INTEGER DEFAULT 0,

                -- Analysis Window
                analysis_start_time TIMESTAMP,
                analysis_end_time TIMESTAMP,
                cycles_analyzed INTEGER DEFAULT 0,

                -- Stats
                live_stats JSON,
                backtest_stats JSON,
                strategy_config JSON,
                comparison_data JSON,

                -- AI Response
                ai_model VARCHAR,
                ai_prompt TEXT,
                ai_response TEXT,

                -- Quality Metrics
                evaluation_score FLOAT,
                key_findings JSON,
                recommendations JSON,

                -- Status
                status VARCHAR DEFAULT 'pending',
                error_message VARCHAR,

                -- Timestamps
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            );
        """))
        print("✓ Table 'live_ai_evaluations' created (or already exists)")

        # Create indexes
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_live_ai_evaluations_session_id ON live_ai_evaluations(session_id);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_live_ai_evaluations_symbol ON live_ai_evaluations(symbol);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_live_ai_evaluations_created_at ON live_ai_evaluations(created_at);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_live_ai_evaluations_status ON live_ai_evaluations(status);
        """))
        print("✓ Indexes created")

        conn.commit()

        # Verify
        result = conn.execute(text("SELECT COUNT(*) FROM live_ai_evaluations"))
        count = result.scalar()
        print(f"✓ Table verified. Current row count: {count}")

    print("\n✅ Migration completed successfully!")

if __name__ == "__main__":
    main()
