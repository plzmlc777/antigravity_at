"""
Database Migration Runner
Run: python -m migrations.run_migrations
"""
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text, inspect
from app.db.session import engine, SessionLocal


def migration_001_add_environment_field():
    """Add 'environment' field and migrate data from is_virtual"""
    with engine.connect() as conn:
        inspector = inspect(engine)
        columns = [col['name'] for col in inspector.get_columns('exchange_accounts')]

        # Check if migration is needed
        if 'environment' in columns:
            print("  [SKIP] 'environment' column already exists")
            return False

        print("  [RUN] Adding 'environment' column...")

        # Add environment column
        conn.execute(text("""
            ALTER TABLE exchange_accounts
            ADD COLUMN environment VARCHAR(20) DEFAULT 'real'
        """))

        # Migrate existing data
        if 'is_virtual' in columns:
            conn.execute(text("""
                UPDATE exchange_accounts
                SET environment = CASE
                    WHEN is_virtual = true THEN 'virtual'
                    ELSE 'real'
                END
            """))
            print("  [OK] Migrated is_virtual -> environment")

        conn.commit()
        return True


def migration_003_add_account_id_to_strategy_configs():
    """Add 'account_id' field to strategy_configs for account-level configurations"""
    with engine.connect() as conn:
        inspector = inspect(engine)
        columns = [col['name'] for col in inspector.get_columns('strategy_configs')]

        # Check if migration is needed
        if 'account_id' in columns:
            print("  [SKIP] 'account_id' column already exists")
            return False

        print("  [RUN] Adding 'account_id' column to strategy_configs...")

        # Add account_id column
        conn.execute(text("""
            ALTER TABLE strategy_configs
            ADD COLUMN account_id INTEGER
        """))

        # Create index
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_strategy_configs_account_id
            ON strategy_configs(account_id)
        """))

        # Assign existing configs to the active account (if any)
        conn.execute(text("""
            UPDATE strategy_configs
            SET account_id = (SELECT id FROM exchange_accounts WHERE is_active = true LIMIT 1)
            WHERE account_id IS NULL
        """))

        conn.commit()
        print("  [OK] Added account_id column and assigned existing configs to active account")
        return True


def run_all_migrations():
    """Run all migrations in order"""
    migrations = [
        ("001_add_environment_field", migration_001_add_environment_field),
        ("003_add_account_id_to_strategy_configs", migration_003_add_account_id_to_strategy_configs),
    ]

    print("=" * 50)
    print("Running Database Migrations")
    print("=" * 50)

    for name, migration_fn in migrations:
        print(f"\nMigration: {name}")
        try:
            result = migration_fn()
            if result:
                print(f"  [SUCCESS] Migration completed")
            else:
                print(f"  [SKIP] Already applied")
        except Exception as e:
            print(f"  [ERROR] {e}")
            raise

    print("\n" + "=" * 50)
    print("All migrations completed!")
    print("=" * 50)


if __name__ == "__main__":
    run_all_migrations()
