"""
Migration script to add AI evaluation settings columns to live_bot_sessions.
Run: python migrate_ai_eval_settings.py
"""
from sqlalchemy import create_engine, text
from app.core.config import settings

def main():
    print(f"Migrating schema on: {settings.POSTGRES_SERVER}")

    port = getattr(settings, 'POSTGRES_PORT', "5432")
    db_uri = f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_SERVER}:{port}/{settings.POSTGRES_DB}"

    engine = create_engine(db_uri)

    with engine.connect() as conn:
        # Add AI evaluation settings columns
        columns = [
            ("ai_eval_enabled", "BOOLEAN DEFAULT FALSE"),
            ("ai_eval_cycles", "INTEGER DEFAULT 10"),
            ("ai_eval_backtest_days", "INTEGER DEFAULT 30"),
            ("ai_eval_mode", "VARCHAR DEFAULT 'paper'"),
        ]

        for col_name, col_def in columns:
            try:
                conn.execute(text(f"""
                    ALTER TABLE live_bot_sessions
                    ADD COLUMN IF NOT EXISTS {col_name} {col_def};
                """))
                print(f"✓ Column '{col_name}' added (or already exists)")
            except Exception as e:
                print(f"✗ Failed to add column '{col_name}': {e}")

        conn.commit()

        # Verify
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'live_bot_sessions'
            AND column_name LIKE 'ai_eval%';
        """))
        cols = [row[0] for row in result]
        print(f"✓ AI eval columns in table: {cols}")

    print("\n✅ Migration completed successfully!")

if __name__ == "__main__":
    main()
