"""
Migration script to create ai_analysis_schedules and ai_analysis_reports tables.
Run: cd backend && python migrate_analysis_scheduler.py
"""
from sqlalchemy import create_engine, text
from app.core.config import settings


def main():
    print(f"Migrating schema on: {settings.POSTGRES_SERVER}")

    port = getattr(settings, 'POSTGRES_PORT', "5432")
    db_uri = f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_SERVER}:{port}/{settings.POSTGRES_DB}"

    engine = create_engine(db_uri)

    with engine.connect() as conn:
        # 1. Create ai_analysis_schedules table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ai_analysis_schedules (
                id VARCHAR PRIMARY KEY,
                user_id INTEGER NOT NULL,
                account_id INTEGER REFERENCES exchange_accounts(id),

                -- Schedule Configuration
                schedule_type VARCHAR NOT NULL,
                schedule_time VARCHAR NOT NULL DEFAULT '15:40',
                schedule_day INTEGER,

                -- Target
                target_sessions JSON,

                -- State
                enabled BOOLEAN DEFAULT TRUE,
                last_run_at TIMESTAMP,
                next_run_at TIMESTAMP,

                -- Timestamps
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))
        print("  Table 'ai_analysis_schedules' created (or already exists)")

        # 2. Create ai_analysis_reports table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ai_analysis_reports (
                id VARCHAR PRIMARY KEY,
                schedule_id VARCHAR REFERENCES ai_analysis_schedules(id),
                user_id INTEGER NOT NULL,

                -- Session Context
                session_id VARCHAR NOT NULL REFERENCES live_bot_sessions(id),
                symbol VARCHAR NOT NULL,
                strategy_name VARCHAR,

                -- Report Type
                report_type VARCHAR DEFAULT 'scheduled',
                status VARCHAR DEFAULT 'pending',

                -- Input Data Snapshots
                trade_summary JSON,
                backtest_comparison JSON,
                strategy_config JSON,

                -- AI Analysis Result
                ai_analysis TEXT,
                ai_model VARCHAR,
                news_data JSON,

                -- Extracted Fields
                grade VARCHAR,
                key_findings JSON,
                recommendations JSON,
                risk_level VARCHAR,
                action VARCHAR,

                -- Notification
                telegram_sent BOOLEAN DEFAULT FALSE,

                -- Error
                error_message TEXT,

                -- Timestamps
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            );
        """))
        print("  Table 'ai_analysis_reports' created (or already exists)")

        # 3. Create indexes
        indexes = [
            ("ix_ai_analysis_schedules_user_id", "ai_analysis_schedules", "user_id"),
            ("ix_ai_analysis_schedules_account_id", "ai_analysis_schedules", "account_id"),
            ("ix_ai_analysis_schedules_enabled", "ai_analysis_schedules", "enabled"),
            ("ix_ai_analysis_reports_schedule_id", "ai_analysis_reports", "schedule_id"),
            ("ix_ai_analysis_reports_user_id", "ai_analysis_reports", "user_id"),
            ("ix_ai_analysis_reports_session_id", "ai_analysis_reports", "session_id"),
            ("ix_ai_analysis_reports_symbol", "ai_analysis_reports", "symbol"),
            ("ix_ai_analysis_reports_created_at", "ai_analysis_reports", "created_at"),
            ("ix_ai_analysis_reports_status", "ai_analysis_reports", "status"),
        ]

        for idx_name, table, column in indexes:
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({column});"))
        print("  Indexes created")

        conn.commit()

        # 4. Verify
        for table in ["ai_analysis_schedules", "ai_analysis_reports"]:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
            count = result.scalar()
            print(f"  Table '{table}' verified. Row count: {count}")

    print("\nMigration completed successfully!")


if __name__ == "__main__":
    main()
