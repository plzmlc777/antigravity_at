"""
Migration: Add owner_id and is_public columns to strategy_info table.
Enables per-user strategy ownership and public/private visibility.

- owner_id: FK to users.id (nullable for backward compat)
- is_public: Boolean (default False = private)
- Existing strategies: assigned to admin user (plzmlc@outlook.com) + public
"""
import sys
sys.path.insert(0, '.')

from app.db.session import engine
from sqlalchemy import text


def migrate():
    with engine.connect() as conn:
        # 1. Add owner_id column
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'strategy_info' AND column_name = 'owner_id'
        """))
        if not result.fetchone():
            conn.execute(text("""
                ALTER TABLE strategy_info
                ADD COLUMN owner_id INTEGER REFERENCES users(id)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_strategy_info_owner_id
                ON strategy_info (owner_id)
            """))
            print("Added: strategy_info.owner_id column")
        else:
            print("Column strategy_info.owner_id already exists, skipping.")

        # 2. Add is_public column
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'strategy_info' AND column_name = 'is_public'
        """))
        if not result.fetchone():
            conn.execute(text("""
                ALTER TABLE strategy_info
                ADD COLUMN is_public BOOLEAN DEFAULT FALSE NOT NULL
            """))
            print("Added: strategy_info.is_public column (default=False)")
        else:
            print("Column strategy_info.is_public already exists, skipping.")

        # 3. Assign existing strategies to admin user + public
        admin_row = conn.execute(text("""
            SELECT id FROM users WHERE email = 'plzmlc@outlook.com'
        """)).fetchone()

        if admin_row:
            admin_id = admin_row[0]
            updated = conn.execute(text("""
                UPDATE strategy_info
                SET owner_id = :admin_id, is_public = TRUE
                WHERE owner_id IS NULL
            """), {"admin_id": admin_id})
            print(f"Updated {updated.rowcount} existing strategies: owner={admin_id}, is_public=True")
        else:
            # Fallback: just make them all public (no owner)
            updated = conn.execute(text("""
                UPDATE strategy_info
                SET is_public = TRUE
                WHERE owner_id IS NULL
            """))
            print(f"Warning: Admin user 'plzmlc@outlook.com' not found. Set {updated.rowcount} strategies to public without owner.")

        conn.commit()
        print("Migration completed successfully!")


if __name__ == "__main__":
    migrate()
