from app.db.session import engine
from sqlalchemy import text
from app.core.config import settings
import sqlalchemy

def migrate_schema():
    print(f"Migrating schema on: {settings.POSTGRES_SERVER}")
    
    # Handle Port logic safely
    port = getattr(settings, 'POSTGRES_PORT', "5432")
    db_uri = f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_SERVER}:{port}/{settings.POSTGRES_DB}"
    
    engine_temp = sqlalchemy.create_engine(db_uri)

    with engine_temp.connect() as conn:
        with conn.begin():
            # Check if column exists
            check_sql = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='strategy_configs' AND column_name='strategy_id';
            """)
            result = conn.execute(check_sql).fetchone()
            
            if not result:
                print("Column 'strategy_id' not found. Adding...")
                conn.execute(text("ALTER TABLE strategy_configs ADD COLUMN strategy_id VARCHAR;"))
                conn.execute(text("CREATE INDEX ix_strategy_configs_strategy_id ON strategy_configs (strategy_id);"))
                conn.execute(text("UPDATE strategy_configs SET strategy_id = 'time_momentum' WHERE strategy_id IS NULL;"))
                print("Column added and indexed successfully.")
            else:
                print("Column 'strategy_id' already exists.")

if __name__ == "__main__":
    migrate_schema()
