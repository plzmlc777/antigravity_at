"""
Migration: Add group_id column to live_bot_sessions table
Purpose: Enable grouping of sessions started together (parallel/exclusive multi-rank)
"""
from app.db.session import engine
from sqlalchemy import text

def migrate():
    with engine.connect() as conn:
        # Check if column already exists
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'live_bot_sessions' AND column_name = 'group_id'
        """))
        existing = [row[0] for row in result]

        if 'group_id' not in existing:
            conn.execute(text("""
                ALTER TABLE live_bot_sessions
                ADD COLUMN group_id VARCHAR(255)
            """))
            print("Added: group_id column to live_bot_sessions")

            # Create index for faster group queries
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_live_bot_sessions_group_id
                ON live_bot_sessions (group_id)
            """))
            print("Created: index on group_id")
        else:
            print("Column group_id already exists, skipping.")

        conn.commit()
        print("Migration completed successfully!")

if __name__ == "__main__":
    migrate()
