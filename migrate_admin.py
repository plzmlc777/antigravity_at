import sys
import os
from sqlalchemy import text

# Add backend directory to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.db.session import engine

def migrate():
    with engine.connect() as conn:
        print("Adding is_admin column if not exists...")
        conn.execute(text('ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE'))
        print("Promoting all existing users to Admin...")
        conn.execute(text('UPDATE users SET is_admin = TRUE'))
        conn.commit()
        print("Migration complete.")

if __name__ == "__main__":
    migrate()
