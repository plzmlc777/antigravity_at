"""
Migration script to add AI API key and model columns to exchange_accounts table.
Run: python migrate_ai_api_key.py
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
        # Check if encrypted_ai_api_key column exists
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'exchange_accounts'
            AND column_name = 'encrypted_ai_api_key'
        """))

        if result.fetchone():
            print("✓ Column 'encrypted_ai_api_key' already exists")
        else:
            conn.execute(text("""
                ALTER TABLE exchange_accounts
                ADD COLUMN encrypted_ai_api_key VARCHAR
            """))
            print("✓ Column 'encrypted_ai_api_key' added to exchange_accounts")

        # Check if encrypted_google_api_key column exists
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'exchange_accounts'
            AND column_name = 'encrypted_google_api_key'
        """))

        if result.fetchone():
            print("✓ Column 'encrypted_google_api_key' already exists")
        else:
            conn.execute(text("""
                ALTER TABLE exchange_accounts
                ADD COLUMN encrypted_google_api_key VARCHAR
            """))
            print("✓ Column 'encrypted_google_api_key' added to exchange_accounts")

        # Check if ai_model column exists
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'exchange_accounts'
            AND column_name = 'ai_model'
        """))

        if result.fetchone():
            print("✓ Column 'ai_model' already exists")
        else:
            conn.execute(text("""
                ALTER TABLE exchange_accounts
                ADD COLUMN ai_model VARCHAR DEFAULT 'claude-sonnet-4-20250514'
            """))
            print("✓ Column 'ai_model' added to exchange_accounts")

        conn.commit()

        # Verify columns
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'exchange_accounts'
            AND column_name IN ('encrypted_ai_api_key', 'encrypted_google_api_key', 'ai_model')
        """))
        columns = [row[0] for row in result.fetchall()]
        print(f"✓ Verified columns: {columns}")

    print("\n✅ Migration completed successfully!")


if __name__ == "__main__":
    main()
