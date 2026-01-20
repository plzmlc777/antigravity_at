
import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add parent directory to sys.path to import app
sys.path.append(os.path.join(os.getcwd(), "backend"))

try:
    from app.core.config import settings
    from app.models.live_trading import LiveBotSession, LiveTradeExecution, LiveRealizedTrade, LiveEquitySnapshot
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

SQLALCHEMY_DATABASE_URL = f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_SERVER}/{settings.POSTGRES_DB}"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def list_and_cleanup():
    db = SessionLocal()
    try:
        sessions = db.query(LiveBotSession).all()
        print(f"Total Sessions: {len(sessions)}")
        
        for s in sessions:
            trade_count = db.query(LiveRealizedTrade).filter(LiveRealizedTrade.session_id == s.id).count()
            print(f"ID: {s.id} | Symbol: {s.symbol} | Strategy: {s.strategy_name} | Status: {s.status} | Trades: {trade_count}")
            
            # Delete if it's a test session OR if it has the specific ID user mentioned (de0e...) OR if it has trades and we want to clear all 'fake' data
            is_fake = (
                s.id.startswith('dummy-session-') or 
                s.id.startswith('test-session-') or
                s.strategy_name in ['seed_strategy', 'VerificationStrategy'] or
                s.symbol in ['TEST-DB', 'TEST-EXEC'] or
                'de0e' in s.id # User's specific session from the snippet
            )
            
            if is_fake:
                print(f"  -> DELETING SESSION: {s.id}")
                db.delete(s)
        
        db.commit()
        print("Cleanup Complete.")
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    list_and_cleanup()
