"""
Migration: Add is_archived column to live_bot_sessions table
Purpose: Allow hiding session groups without deleting trade history
"""
from app.db.session import engine
from sqlalchemy import text

def migrate():
    with engine.connect() as conn:
        # Check if column already exists
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'live_bot_sessions' AND column_name = 'is_archived'
        """))
        existing = [row[0] for row in result]

        if 'is_archived' not in existing:
            conn.execute(text("""
                ALTER TABLE live_bot_sessions
                ADD COLUMN is_archived BOOLEAN DEFAULT FALSE
            """))
            print("Added: is_archived column to live_bot_sessions")
        else:
            print("Column is_archived already exists, skipping.")

        conn.commit()
        print("Migration completed successfully!")

if __name__ == "__main__":
    migrate()
