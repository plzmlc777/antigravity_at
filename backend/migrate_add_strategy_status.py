"""
Migration: Add status column to strategy_info table.
Enables test-then-activate workflow for Strategy Lab.

- Existing strategies get status='active' (visible in Profiles)
- New strategies from Strategy Lab start as status='testing'
"""
import sys
sys.path.insert(0, '.')

from app.db.session import engine
from sqlalchemy import text


def migrate():
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'strategy_info' AND column_name = 'status'
        """))

        if not result.fetchone():
            conn.execute(text("""
                ALTER TABLE strategy_info
                ADD COLUMN status VARCHAR(50) DEFAULT 'active' NOT NULL
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_strategy_info_status
                ON strategy_info (status)
            """))
            print("Added: strategy_info.status column (default='active')")
            print("Created: index ix_strategy_info_status")
        else:
            print("Column strategy_info.status already exists, skipping.")

        conn.commit()
        print("Migration completed successfully!")


if __name__ == "__main__":
    migrate()
