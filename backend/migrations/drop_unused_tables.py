"""
Migration: Drop unused tables

This migration drops tables that are no longer used:
- trading_bots: Legacy simple bot orchestrator (replaced by live_bot_sessions)
- strategy_configs: Legacy strategy config storage (replaced by strategy_profiles)

Run: python -m migrations.drop_unused_tables

WARNING: This will permanently delete these tables and their data!
Make sure you have a backup before running.
"""
from app.db.session import engine
from sqlalchemy import text

def migrate():
    with engine.connect() as conn:
        # Check existing tables
        result = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """))
        existing_tables = {row[0] for row in result}
        print(f"Current tables: {sorted(existing_tables)}")
        print()

        # Drop trading_bots table
        if 'trading_bots' in existing_tables:
            # Check if table has data
            count_result = conn.execute(text("SELECT COUNT(*) FROM trading_bots"))
            count = count_result.scalar()
            print(f"trading_bots table: {count} rows")

            print("Dropping trading_bots table...")
            conn.execute(text("DROP TABLE trading_bots CASCADE"))
            print("✓ Dropped: trading_bots")
        else:
            print("✓ trading_bots already dropped")

        # Drop strategy_configs table
        if 'strategy_configs' in existing_tables:
            # Check if table has data
            count_result = conn.execute(text("SELECT COUNT(*) FROM strategy_configs"))
            count = count_result.scalar()
            print(f"strategy_configs table: {count} rows")

            print("Dropping strategy_configs table...")
            conn.execute(text("DROP TABLE strategy_configs CASCADE"))
            print("✓ Dropped: strategy_configs")
        else:
            print("✓ strategy_configs already dropped")

        conn.commit()
        print("\n✓ Migration completed successfully!")

        # Verify
        result = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """))
        remaining_tables = [row[0] for row in result]
        print(f"\nRemaining tables: {remaining_tables}")

if __name__ == "__main__":
    migrate()
