
import asyncio
import logging
import sys
import os

# Ensure backend path is in sys.path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.core.live_manager import live_manager
from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.models.live_trading import LiveBotSession, SessionStatus

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def verify_live_manager():
    logger.info("--- Starting LiveManager Verification ---")
    
    # 1. Reset Tables (Clean Slate)
    logger.info("Resetting DB Tables...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    # 2. Test Start Session
    logger.info("Testing start_session()...")
    config = {
        "symbol": "005930",
        "strategy_name": "time_momentum",
        "strategy_config": {"target_profit": 0.02},
        "initial_capital": 10000000
    }
    
    try:
        session_id = await live_manager.start_session(config)
        logger.info(f"Session Started ID: {session_id}")
    except Exception as e:
        logger.error(f"FAILURE in start_session: {e}")
        traceback.print_exc()
        return

    # 3. Verify DB Record
    db = SessionLocal()
    sess = db.query(LiveBotSession).filter_by(id=session_id).first()
    if sess:
        logger.info(f"DB Record Found: symbol={sess.symbol}, status={sess.status}, interval={sess.interval}")
        if sess.interval != "1m":
             logger.error("Interval default missing!")
    else:
        logger.error("DB Record NOT Found!")
    db.close()

    # 4. Test Get Status
    logger.info("Testing get_status()...")
    status_list = live_manager.get_status(session_id)
    logger.info(f"Status List: {status_list}")
    if not status_list:
        logger.error("Status list empty!")
        
    # 5. Test Stop Session
    logger.info("Testing stop_session()...")
    await live_manager.stop_session(session_id)
    
    # 6. Verify Stop State
    db = SessionLocal()
    sess = db.query(LiveBotSession).filter_by(id=session_id).first()
    if sess.status == SessionStatus.STOPPED:
         logger.info("Session correctly marked STOPPED")
    else:
         logger.error(f"Session status incorrect: {sess.status}")
    db.close()
    
    logger.info("--- Verification Complete ---")

if __name__ == "__main__":
    import traceback
    try:
        asyncio.run(verify_live_manager())
    except Exception as e:
        logger.error(f"Top Level Error: {e}")
