
import asyncio
import logging
import uuid
import traceback
from typing import Dict, Any, List, Optional
from datetime import datetime

from ..core.live_engine import LiveTradingEngine
from ..adapters.kiwoom_real import KiwoomRealAdapter
from ..adapters.kiwoom_mock import KiwoomMockAdapter
from ..strategies.time_momentum import TimeMomentumStrategy 
from ..core.config import settings
from ..db.session import SessionLocal
from ..models.live_trading import LiveBotSession, SessionStatus

logger = logging.getLogger("LiveManager")

class LiveManager:
    """
    Singleton Manager for LiveTradingEngines.
    """
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = LiveManager()
        return cls._instance

    def __init__(self):
        self.engines: Dict[str, LiveTradingEngine] = {} # session_id -> Engine
        
        if settings.TRADING_MODE == "MOCK":
            logger.info("LiveManager: Using KIWOOM MOCK ADAPTER")
            self.adapter = KiwoomMockAdapter()
        else:
            logger.info("LiveManager: Using KIWOOM REAL ADAPTER")
            self.adapter = KiwoomRealAdapter()
            
        # Note: In real production, adapter might need to be singleton too.
        # Note: In real production, adapter might need to be singleton too.
        # KiwoomRealAdapter in this project seems to be stateless http wrapper?
        # If it holds WebSocket state, it must be shared carefully.
        
    async def initialize(self):
        """
        Load active sessions from DB on server startup.
        """
        db = SessionLocal()
        try:
            # Find RUNNING sessions
            active_sessions = db.query(LiveBotSession).filter(
                LiveBotSession.status == SessionStatus.RUNNING
            ).all()
            
            for sess in active_sessions:
                try:
                    logger.info(f"Restoring Live Session: {sess.id} ({sess.symbol})")
                    await self._restore_engine(sess)
                except Exception as e:
                    logger.error(f"Failed to restore session {sess.id}: {e}")
                    traceback.print_exc()
                    sess.status = SessionStatus.ERROR
                    sess.error_log = str(e)
                    db.commit()
        finally:
            db.close()

    async def start_session(self, config: Dict[str, Any]) -> str:
        """
        Create and Start a new Live Session.
        config: {
            "symbol": str,
            "strategy_name": str,
            "strategy_config": dict,
            "initial_capital": float
        }
        """
        session_id = str(uuid.uuid4())
        symbol = config.get("symbol")
        strategy_name = config.get("strategy_name", "time_momentum")
        strat_config = config.get("strategy_config", {})
        initial_capital = config.get("initial_capital", 10000000)
        
        # 1. DB Record
        db = SessionLocal()
        try:
            sess = LiveBotSession(
                id=session_id,
                symbol=symbol,
                strategy_name=strategy_name,
                strategy_config=strat_config,
                initial_capital=initial_capital,
                status=SessionStatus.RUNNING, # Optimistic
                started_at=datetime.now(),
                interval="1m" # Default to 1m for now
            )
            db.add(sess)
            db.commit()
        except Exception as e:
            db.close()
            raise e
        
        # 2. Engine Create & Start
        try:
            # Resolve Strategy Class
            # TODO: Robust Factory
            StrategyClass = TimeMomentumStrategy 
            
            engine = LiveTradingEngine(session_id, StrategyClass, strat_config, self.adapter)
            await engine.initialize()
            
            self.engines[session_id] = engine
            asyncio.create_task(engine.run_loop())
            
            logger.info(f"Started Live Session {session_id}")
            return session_id
            
        except Exception as e:
            # Revert DB status
            sess.status = SessionStatus.ERROR
            sess.error_log = str(e)
            db.commit()
            db.close()
            raise e
        finally:
            if db: db.close()

    async def stop_session(self, session_id: str):
        if session_id in self.engines:
            logger.info(f"Stopping Live Session {session_id}...")
            engine = self.engines[session_id]
            engine.stop()
            del self.engines[session_id]
            
        # Update DB
        db = SessionLocal()
        try:
            sess = db.query(LiveBotSession).filter_by(id=session_id).first()
            if sess:
                sess.status = SessionStatus.STOPPED
                sess.end_time = datetime.now()
                db.commit()
        finally:
            db.close()

    def get_status(self, session_id: str = None) -> List[Dict]:
        """
        Return status of specific session or all managed sessions.
        """
        results = []
        targets = [session_id] if session_id else self.engines.keys()
        
        for sid in targets:
            if sid not in self.engines: continue
            eng = self.engines[sid]
            
            # Context Summary
            pnl = (eng.context.cash + sum(eng.context.holdings.values()) * eng.context.get_current_price(eng.symbol)) - eng.context.initial_capital
            
            results.append({
                "session_id": sid,
                "symbol": eng.symbol,
                "is_running": eng.is_running,
                "current_price": eng.context.get_current_price(eng.symbol),
                "pnl": pnl,
                "trades_count": len(eng.context.trades),
                "last_update": datetime.now().isoformat()
            })
        return results

    async def _restore_engine(self, sess: LiveBotSession):
        StrategyClass = TimeMomentumStrategy 
        engine = LiveTradingEngine(sess.id, StrategyClass, sess.strategy_config, self.adapter)
        await engine.initialize()
        self.engines[sess.id] = engine
        asyncio.create_task(engine.run_loop())

    async def subscribe_to_session(self, session_id: str, queue: asyncio.Queue):
        """
        Subscribe a WebSocket Queue to a Session's Real-time Events.
        """
        if session_id not in self.engines:
            # If session not active, maybe return error or empty?
            # For now, just raise
            raise ValueError(f"Session {session_id} is not running")
            
        engine = self.engines[session_id]
        
        # 0. Send Initial History immediately
        history = engine.get_history()
        if history:
             await queue.put({
                 "type": "history",
                 "data": history
             })
        
        # 1. Define Listeners
        async def on_tick(data):
            await queue.put(data)
            
        async def on_candle(data):
            await queue.put(data)
            
        # 2. Attach
        engine.add_tick_listener(on_tick)
        engine.add_candle_listener(on_candle)
        
        return on_tick, on_candle # Return so caller can unsubscribe later

    def unsubscribe_from_session(self, session_id: str, listeners: tuple):
        """
        Unsubscribe listeners.
        """
        if session_id in self.engines:
            engine = self.engines[session_id]
            tick_l, candle_l = listeners
            engine.remove_tick_listener(tick_l)
            engine.remove_candle_listener(candle_l)

# Global Access
live_manager = LiveManager.get_instance()
