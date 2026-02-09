"""
Migration script to add Telegram notification columns to exchange_accounts table.
Run: python migrate_telegram_settings.py
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
        # Add Telegram columns to exchange_accounts table
        columns = [
            ("encrypted_telegram_bot_token", "VARCHAR", None),
            ("telegram_chat_id", "VARCHAR", None),
            ("telegram_enabled", "BOOLEAN", "FALSE"),
            ("telegram_notify_trades", "BOOLEAN", "TRUE"),
            ("telegram_notify_ai_eval", "BOOLEAN", "TRUE"),
            ("telegram_notify_errors", "BOOLEAN", "TRUE"),
        ]

        for col_name, col_type, default in columns:
            try:
                if default:
                    conn.execute(text(f"""
                        ALTER TABLE exchange_accounts
                        ADD COLUMN IF NOT EXISTS {col_name} {col_type} DEFAULT {default};
                    """))
                else:
                    conn.execute(text(f"""
                        ALTER TABLE exchange_accounts
                        ADD COLUMN IF NOT EXISTS {col_name} {col_type};
                    """))
                print(f"✓ Column '{col_name}' added (or already exists)")
            except Exception as e:
                print(f"✗ Failed to add column '{col_name}': {e}")

        conn.commit()

        # Verify columns
        result = conn.execute(text("""
            SELECT column_name, data_type, column_default
            FROM information_schema.columns
            WHERE table_name = 'exchange_accounts'
            AND column_name LIKE 'telegram%'
            ORDER BY column_name;
        """))
        rows = result.fetchall()
        print(f"\n✓ Telegram columns in exchange_accounts: {len(rows)}")
        for row in rows:
            print(f"  - {row[0]}: {row[1]} (default: {row[2]})")

    print("\n✅ Migration completed successfully!")


if __name__ == "__main__":
    main()
