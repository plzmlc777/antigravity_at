"""
Migration script to create trading_error_logs table.
Run: python migrate_error_log_table.py
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
        # Create trading_error_logs table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS trading_error_logs (
                id VARCHAR PRIMARY KEY,
                session_id VARCHAR,
                symbol VARCHAR,
                error_type VARCHAR NOT NULL,
                severity VARCHAR DEFAULT 'ERROR',
                error_message VARCHAR NOT NULL,
                stack_trace TEXT,
                context_data JSON,
                source_file VARCHAR,
                source_function VARCHAR,
                is_resolved BOOLEAN DEFAULT FALSE,
                resolution_note VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP
            );
        """))
        print("✓ Table 'trading_error_logs' created (or already exists)")

        # Create indexes
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_trading_error_logs_session_id ON trading_error_logs(session_id);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_trading_error_logs_symbol ON trading_error_logs(symbol);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_trading_error_logs_error_type ON trading_error_logs(error_type);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_trading_error_logs_severity ON trading_error_logs(severity);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_trading_error_logs_created_at ON trading_error_logs(created_at);
        """))
        print("✓ Indexes created")

        conn.commit()

        # Verify
        result = conn.execute(text("SELECT COUNT(*) FROM trading_error_logs"))
        count = result.scalar()
        print(f"✓ Table verified. Current row count: {count}")

    print("\n✅ Migration completed successfully!")

if __name__ == "__main__":
    main()
