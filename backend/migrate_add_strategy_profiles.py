"""
Migration: Create strategy_profiles table
Purpose: Store complete multi-rank strategy configurations as reusable profiles
"""
from app.db.session import engine
from sqlalchemy import text

def migrate():
    with engine.connect() as conn:
        # Check if table already exists
        result = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_name = 'strategy_profiles'
        """))
        existing = [row[0] for row in result]

        if 'strategy_profiles' not in existing:
            conn.execute(text("""
                CREATE TABLE strategy_profiles (
                    id VARCHAR(255) PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    strategy_name VARCHAR(255) NOT NULL,
                    rank_configs JSONB NOT NULL,
                    execution_mode VARCHAR(50) DEFAULT 'parallel',
                    rank_weights JSONB,
                    initial_capital FLOAT DEFAULT 10000000,
                    is_paper BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE
                )
            """))
            print("Created: strategy_profiles table")

            # Create indexes
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_strategy_profiles_user_id
                ON strategy_profiles (user_id)
            """))
            print("Created: index on user_id")

            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_strategy_profiles_strategy_name
                ON strategy_profiles (strategy_name)
            """))
            print("Created: index on strategy_name")
        else:
            print("Table strategy_profiles already exists, skipping.")

        conn.commit()
        print("Migration completed successfully!")

if __name__ == "__main__":
    migrate()
