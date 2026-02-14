"""
Migration: Create strategy_requests table
Purpose: Store user-submitted strategy ideas for semi-automatic implementation
"""
from app.db.session import engine
from sqlalchemy import text


def migrate():
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'strategy_requests'"
        ))
        existing = [row[0] for row in result]

        if 'strategy_requests' not in existing:
            conn.execute(text("""
                CREATE TABLE strategy_requests (
                    id VARCHAR(255) PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    name VARCHAR(255) NOT NULL,
                    strategy_id VARCHAR(255),
                    description TEXT,
                    entry_type VARCHAR(50) DEFAULT 'price',
                    entry_condition TEXT NOT NULL,
                    indicators JSONB,
                    entry_mode VARCHAR(50) DEFAULT 'single',
                    additional_entry TEXT,
                    exit_condition TEXT,
                    custom_parameters JSONB,
                    default_overrides JSONB,
                    notes TEXT,
                    status VARCHAR(50) DEFAULT 'draft',
                    implemented_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            print("Created: strategy_requests table")

            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_strategy_requests_user_id ON strategy_requests (user_id)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_strategy_requests_status ON strategy_requests (status)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_strategy_requests_created_at ON strategy_requests (created_at)"
            ))
            print("Created: indexes on user_id, status, created_at")
        else:
            print("Table strategy_requests already exists, skipping.")

        conn.commit()
        print("Migration completed successfully!")


if __name__ == "__main__":
    migrate()
