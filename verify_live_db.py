
import asyncio
from backend.app.db.session import engine, SessionLocal
from backend.app.db.base import Base
from backend.app.models.live_trading import LiveBotSession, LiveTradeExecution
from sqlalchemy import inspect
from datetime import datetime

def verify_db():
    print("--- Verifying Live Trading Database ---")
    
    # 1. Connect and Inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"Existing Tables: {tables}")
    
    # Always recreate in Dev to ensure schema matches model
    print("Recreating tables to apply schema changes...")
    import backend.app.models.live_trading
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("Tables created.")
        
    # 2. CRUD Test
    db = SessionLocal()
    try:
        # Create Session
        dummy_session = LiveBotSession(
            symbol="TEST-DB",
            strategy_name="VerificationStrategy",
            strategy_config={"param": 1},
            interval="1m",
            status="TESTING",
            initial_capital=1000000
        )
        db.add(dummy_session)
        db.commit()
        db.refresh(dummy_session)
        print(f"Created Dummy Session: {dummy_session.id}")
        
        # Create Execution
        dummy_exec = LiveTradeExecution(
            session_id=dummy_session.id,
            symbol="TEST-EXEC",
            signal_type="BUY",
            signal_timestamp=datetime.utcnow(),
            theoretical_price=100.0,
            requested_quantity=10,
            executed_price=101.0,
            filled_quantity=10,
            status="FILLED"
        )
        db.add(dummy_exec)
        db.commit()
        print(f"Created Dummy Execution for Session {dummy_session.id}")
        
        # Read Back
        s = db.query(LiveBotSession).filter_by(id=dummy_session.id).first()
        assert s is not None
        assert len(s.executions) == 1
        assert s.executions[0].executed_price == 101.0
        print("Read Backend Verification: PASS")
        
        # Cleanup
        db.delete(dummy_exec)
        db.delete(dummy_session)
        db.commit()
        print("Cleanup: PASS")
        
    except Exception as e:
        print(f"CRUD Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    verify_db()
