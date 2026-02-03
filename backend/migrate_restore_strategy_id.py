
import logging
from sqlalchemy import create_engine, text, inspect
# Import settings correctly
from app.core.config import settings

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate():
    # Construct DB URL using settings
    # Construct DB URL manually (Default port 5432 if missing)
    port = getattr(settings, 'POSTGRES_PORT', "5432")
    SQLALCHEMY_DATABASE_URL = f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_SERVER}:{port}/{settings.POSTGRES_DB}"
    
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
    
    try:
        # Create inspector
        inspector = inspect(engine)
        columns = [c['name'] for c in inspector.get_columns('strategy_configs')]
        
        if 'strategy_id' not in columns:
            logger.info("Adding 'strategy_id' column to 'strategy_configs' table...")
            with engine.connect() as conn:
                # Add column
                conn.execute(text("ALTER TABLE strategy_configs ADD COLUMN strategy_id VARCHAR DEFAULT 'time_momentum'"))
                # Create Index (Separate step for safety)
                conn.execute(text("CREATE INDEX ix_strategy_configs_strategy_id ON strategy_configs (strategy_id)"))
                conn.commit()
            logger.info("Migration successful: Added 'strategy_id' column.")
        else:
            logger.info("'strategy_id' column already exists. Skipping.")
            
    except Exception as e:
        logger.error(f"Migration failed: {e}")

if __name__ == "__main__":
    migrate()
