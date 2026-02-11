"""
Migration: Remove legacy columns from exchange_accounts table

This migration removes columns that have been migrated to profile-level storage:
- symbol_compare_settings: Now stored in strategy_profiles.symbol_compare_settings
- execution_mode: Now stored in strategy_profiles.execution_mode

Run: python -m migrations.remove_legacy_columns
"""
from app.db.session import engine
from sqlalchemy import text

def migrate():
    with engine.connect() as conn:
        # Check current columns
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'exchange_accounts'
        """))
        existing = {row[0] for row in result}
        print(f"Current columns in exchange_accounts: {sorted(existing)}")

        # Remove symbol_compare_settings if exists
        if 'symbol_compare_settings' in existing:
            print("Removing symbol_compare_settings column from exchange_accounts...")
            conn.execute(text("ALTER TABLE exchange_accounts DROP COLUMN symbol_compare_settings"))
            print("✓ Removed: symbol_compare_settings")
        else:
            print("✓ symbol_compare_settings already removed")

        # Remove execution_mode if exists
        if 'execution_mode' in existing:
            print("Removing execution_mode column from exchange_accounts...")
            conn.execute(text("ALTER TABLE exchange_accounts DROP COLUMN execution_mode"))
            print("✓ Removed: execution_mode")
        else:
            print("✓ execution_mode already removed")

        conn.commit()
        print("\n✓ Migration completed successfully!")

        # Verify
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'exchange_accounts'
            ORDER BY column_name
        """))
        remaining = [row[0] for row in result]
        print(f"\nRemaining columns: {remaining}")

if __name__ == "__main__":
    migrate()
