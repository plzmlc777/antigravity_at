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


def migration_002_add_last_selected_strategy():
    """Add 'last_selected_strategy_id' field to exchange_accounts"""
    with engine.connect() as conn:
        inspector = inspect(engine)
        columns = [col['name'] for col in inspector.get_columns('exchange_accounts')]

        # Check if migration is needed
        if 'last_selected_strategy_id' in columns:
            print("  [SKIP] 'last_selected_strategy_id' column already exists")
            return False

        print("  [RUN] Adding 'last_selected_strategy_id' column...")

        # Add last_selected_strategy_id column
        conn.execute(text("""
            ALTER TABLE exchange_accounts
            ADD COLUMN last_selected_strategy_id VARCHAR(50)
        """))

        conn.commit()
        print("  [OK] Added 'last_selected_strategy_id' column")
        return True


def migration_003_add_watchlist_and_settings():
    """Add watchlist and symbol compare settings to exchange_accounts"""
    with engine.connect() as conn:
        inspector = inspect(engine)
        columns = [col['name'] for col in inspector.get_columns('exchange_accounts')]

        added_any = False

        # 1. last_symbol
        if 'last_symbol' not in columns:
            print("  [RUN] Adding 'last_symbol' column...")
            conn.execute(text("""
                ALTER TABLE exchange_accounts
                ADD COLUMN last_symbol VARCHAR(20) DEFAULT '005930'
            """))
            added_any = True
            print("  [OK] Added 'last_symbol' column")
        else:
            print("  [SKIP] 'last_symbol' column already exists")

        # 2. saved_symbols (JSON)
        if 'saved_symbols' not in columns:
            print("  [RUN] Adding 'saved_symbols' column...")
            conn.execute(text("""
                ALTER TABLE exchange_accounts
                ADD COLUMN saved_symbols JSONB
            """))
            added_any = True
            print("  [OK] Added 'saved_symbols' column")
        else:
            print("  [SKIP] 'saved_symbols' column already exists")

        # 3. symbol_compare_settings (JSON)
        if 'symbol_compare_settings' not in columns:
            print("  [RUN] Adding 'symbol_compare_settings' column...")
            conn.execute(text("""
                ALTER TABLE exchange_accounts
                ADD COLUMN symbol_compare_settings JSONB
            """))
            added_any = True
            print("  [OK] Added 'symbol_compare_settings' column")
        else:
            print("  [SKIP] 'symbol_compare_settings' column already exists")

        # 4. execution_mode
        if 'execution_mode' not in columns:
            print("  [RUN] Adding 'execution_mode' column...")
            conn.execute(text("""
                ALTER TABLE exchange_accounts
                ADD COLUMN execution_mode VARCHAR(20) DEFAULT 'exclusive'
            """))
            added_any = True
            print("  [OK] Added 'execution_mode' column")
        else:
            print("  [SKIP] 'execution_mode' column already exists")

        if added_any:
            conn.commit()

        return added_any


def migration_004_add_account_keepalive_logs():
    """Create account_keepalive_logs table (daily ping results for real exchange accounts)."""
    with engine.connect() as conn:
        inspector = inspect(engine)
        existing = inspector.get_table_names()

        if 'account_keepalive_logs' in existing:
            print("  [SKIP] 'account_keepalive_logs' table already exists")
            return False

        print("  [RUN] Creating 'account_keepalive_logs' table...")
        # NOTE: account_id is a logical reference to exchange_accounts.id but no
        # FK constraint is declared, because some prod databases (mint) have
        # exchange_accounts.id without a PRIMARY KEY / UNIQUE constraint, which
        # would cause `REFERENCES exchange_accounts(id)` to fail. The worker
        # script always sources account_id from a live ExchangeAccount row, so
        # referential integrity is enforced at the application layer.
        conn.execute(text("""
            CREATE TABLE account_keepalive_logs (
                id SERIAL PRIMARY KEY,
                account_id INTEGER NOT NULL,
                ping_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                success BOOLEAN NOT NULL,
                latency_ms INTEGER,
                cash_summary JSONB,
                holdings_count INTEGER,
                error_msg TEXT
            )
        """))
        conn.execute(text("""
            CREATE INDEX ix_keepalive_account_ping
            ON account_keepalive_logs (account_id, ping_at DESC)
        """))
        conn.commit()
        print("  [OK] Created 'account_keepalive_logs' table + index")
        return True


def run_all_migrations():
    """Run all migrations in order"""
    migrations = [
        ("001_add_environment_field", migration_001_add_environment_field),
        ("002_add_last_selected_strategy", migration_002_add_last_selected_strategy),
        ("003_add_watchlist_and_settings", migration_003_add_watchlist_and_settings),
        ("004_add_account_keepalive_logs", migration_004_add_account_keepalive_logs),
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
