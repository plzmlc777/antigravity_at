"""
Migration script to create optimization_analysis table for AI analysis.
Run: python migrate_optimization_analysis.py
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
        # Create optimization_analysis table (for imported CSV data)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS optimization_analysis (
                id SERIAL PRIMARY KEY,
                analysis_id UUID NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                -- Basic info
                rank INTEGER,
                symbol VARCHAR(20),

                -- Metrics (stored as FLOAT for SQL aggregations)
                score FLOAT,
                total_return FLOAT,
                win_rate FLOAT,
                total_trades INTEGER,
                max_drawdown FLOAT,
                profit_factor FLOAT,
                sharpe_ratio FLOAT,
                avg_pnl FLOAT,
                stability_score FLOAT,
                acceleration_score FLOAT,
                activity_rate FLOAT,
                avg_holding_time FLOAT,
                max_profit FLOAT,
                max_loss FLOAT,
                total_days INTEGER,

                -- Cycle metrics
                cycle_count INTEGER,
                cycle_avg_pnl FLOAT,
                cycle_avg_hold FLOAT,

                -- Strategy parameters (flexible JSONB)
                config JSONB
            );
        """))
        print("✓ Table 'optimization_analysis' created (or already exists)")

        # Create indexes for fast querying
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_opt_analysis_id ON optimization_analysis(analysis_id);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_opt_analysis_symbol ON optimization_analysis(symbol);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_opt_analysis_score ON optimization_analysis(score DESC);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_opt_analysis_total_return ON optimization_analysis(total_return DESC);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_opt_analysis_stability ON optimization_analysis(stability_score DESC);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_opt_analysis_created ON optimization_analysis(created_at);
        """))
        print("✓ Indexes created")

        # Create AI analysis sessions table (metadata about each analysis run)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ai_analysis_sessions (
                id UUID PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                csv_filename VARCHAR(255),
                strategy_id VARCHAR(100),
                total_rows INTEGER,
                symbols_count INTEGER,

                -- Analysis results
                ai_score_formula TEXT,
                ai_analysis_text TEXT,
                ai_recommendations JSONB,

                -- Status
                status VARCHAR(50) DEFAULT 'pending',
                completed_at TIMESTAMP,
                error_message TEXT
            );
        """))
        print("✓ Table 'ai_analysis_sessions' created (or already exists)")

        conn.commit()

        # Verify
        result = conn.execute(text("SELECT COUNT(*) FROM optimization_analysis"))
        count = result.scalar()
        print(f"✓ Table 'optimization_analysis' verified. Current row count: {count}")

        result = conn.execute(text("SELECT COUNT(*) FROM ai_analysis_sessions"))
        count = result.scalar()
        print(f"✓ Table 'ai_analysis_sessions' verified. Current row count: {count}")

    print("\n✅ Migration completed successfully!")


if __name__ == "__main__":
    main()
