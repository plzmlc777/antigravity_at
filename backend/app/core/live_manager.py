
import asyncio
import logging
import uuid
import traceback
from typing import Dict, Any, List, Optional
from datetime import datetime

from ..core.live_engine import LiveTradingEngine
from ..adapters.kiwoom_real import KiwoomRealAdapter
from ..adapters.kiwoom_mock import KiwoomMockAdapter
# from ..strategies.time_momentum import TimeMomentumStrategy # Removed
from ..core.config import settings
from ..db.session import SessionLocal
from ..models.live_trading import LiveBotSession, SessionStatus
from ..models.strategy_config import StrategyConfig
from ..core.market_data_router import market_data_router

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
            self.adapter = KiwoomRealAdapter()
            # Register Global Tick Listener
            if hasattr(self.adapter, "add_tick_listener"):
                self.adapter.add_tick_listener(self._on_tick)
            # Bind this adapter's callback to the singleton WebSocket
            # Must be called AFTER add_tick_listener so the listener is registered
            if hasattr(self.adapter, "setup_realtime_callbacks"):
                self.adapter.setup_realtime_callbacks()

    def _on_tick(self, tick_data: Dict):
        """
        Route global tick to specific engine
        """
        symbol = tick_data.get("symbol")
        if not symbol: return

        for engine in self.engines.values():
            if engine.symbol == symbol:
                asyncio.create_task(engine.process_realtime_tick(tick_data))

        # KiwoomRealAdapter in this project seems to be stateless http wrapper?
        # If it holds WebSocket state, it must be shared carefully.
        
    async def initialize(self):
        """
        Load active sessions from DB on server startup.
        """
        # Connect to MarketRouter
        market_data_router.set_live_manager(self)

        # Ensure token is ready BEFORE restoring sessions (prevents "Cannot start Realtime: No Token")
        if hasattr(self.adapter, '_ensure_token'):
            logger.info("LiveManager: Acquiring Kiwoom token before session restore...")
            for attempt in range(3):
                try:
                    await self.adapter._ensure_token()
                    if self.adapter.access_token:
                        logger.info("LiveManager: Token acquired successfully.")
                        break
                except Exception as e:
                    logger.warning(f"Token acquisition attempt {attempt + 1} failed: {e}")
                await asyncio.sleep(2)
            else:
                logger.error("LiveManager: Failed to acquire token after 3 attempts. Sessions may not have real-time data.")

        db = SessionLocal()
        try:
            # 1. Restore sessions that were already RUNNING
            active_sessions = db.query(LiveBotSession).filter(
                LiveBotSession.status == SessionStatus.RUNNING
            ).all()
            
            restored_ids = set()
            for sess in active_sessions:
                try:
                    logger.info(f"Restoring Live Session: {sess.id} ({sess.symbol})")
                    await self._restore_engine(sess)
                    restored_ids.add(sess.id)
                except Exception as e:
                    logger.error(f"Failed to restore session {sess.id}: {e}")
                    traceback.print_exc()
                    sess.status = SessionStatus.ERROR
                    sess.error_log = str(e)
                    db.commit()

            # NOTE: Auto-Start logic removed in v0.9.7.3 due to duplicate key errors
            # and conflicts with existing RUNNING sessions. Users must manually start strategies.
                    
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
        session_id = config.get("session_id") or str(uuid.uuid4())
        symbol = config.get("symbol")
        strategy_name = config.get("strategy_name", "time_momentum")
        strat_config = config.get("strategy_config", {})
        initial_capital = config.get("initial_capital", 0)
        is_paper = config.get("is_paper", True)
        
        # 1. DB Record
        db = SessionLocal()
        try:
            sess = LiveBotSession(
                id=session_id,
                symbol=symbol,
                strategy_name=strategy_name,
                strategy_config=strat_config,
                initial_capital=initial_capital,
                is_paper=is_paper,
                is_active=True,
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
            # Note: Strategy class resolution moved inside LiveTradingEngine.initialize()
            engine = LiveTradingEngine(session_id, self.adapter)
            await engine.initialize()
            
            self.engines[session_id] = engine
            asyncio.create_task(engine.run_loop())
            
            # Start Real-time Data Stream for this symbol
            if hasattr(self.adapter, "start_realtime"):
                asyncio.create_task(self.adapter.start_realtime([symbol]))
            
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
                sess.is_active = False # Deactivate so it's not restored
                sess.stopped_at = datetime.now()
                db.commit()
        finally:
            db.close()

    async def toggle_orders(self, session_id: str, enabled: bool):
        """
        Enable or Disable actual order execution for a session.
        """
        # 1. Update running engine
        if session_id in self.engines:
            self.engines[session_id].toggle_orders(enabled)
            
        # 2. Update DB
        db = SessionLocal()
        try:
            sess = db.query(LiveBotSession).filter_by(id=session_id).first()
            if sess:
                sess.orders_enabled = enabled
                db.commit()
                logger.info(f"Session {session_id}: Orders {'Enabled' if enabled else 'Disabled'} (DB Updated)")
        finally:
            db.close()

    async def toggle_mode(self, session_id: str, is_paper: bool):
        """
        Switch between Paper (Simulated) and Real (Live) trading.
        """
        # 1. Update running engine
        if session_id in self.engines:
            self.engines[session_id].toggle_mode(is_paper)
            
        # 2. Update DB
        db = SessionLocal()
        try:
            sess = db.query(LiveBotSession).filter_by(id=session_id).first()
            if sess:
                sess.is_paper = is_paper
                db.commit()
                logger.info(f"Session {session_id}: Mode set to {'PAPER' if is_paper else 'REAL'} (DB Updated)")
        finally:
            db.close()

    async def liquidate_session(self, session_id: str):
        """
        Emergency Liquidation: Market Sell and Pause Trading.
        """
        # 1. Trigger Engine Liquidation
        if session_id in self.engines:
            await self.engines[session_id].liquidate_all()
            
        # 2. Persist orders_enabled = False in DB
        db = SessionLocal()
        try:
            sess = db.query(LiveBotSession).filter_by(id=session_id).first()
            if sess:
                sess.orders_enabled = False
                db.commit()
                logger.info(f"Session {session_id}: Force-Disabled Orders in DB after liquidation.")
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
            
            # Context Summary (Isolated PnL based on trades)
            pnl = eng.context.calculate_pnl()
            
            results.append({
                "session_id": sid,
                "symbol": eng.symbol,
                "strategy_name": getattr(eng, 'strategy_name', 'unknown'),
                "is_running": eng.is_running,
                "orders_enabled": eng.orders_enabled,
                "is_paper": getattr(eng, 'is_paper', True),
                "current_price": eng.context.get_current_price(eng.symbol),
                "pnl": pnl,
                "trades_count": len(eng.context.trades),
                "last_update": datetime.now().isoformat()
            })
        return results

    async def _restore_engine(self, sess: LiveBotSession):
        # engine = LiveTradingEngine(sess.id, StrategyClass, sess.strategy_config, self.adapter) # Old
        engine = LiveTradingEngine(sess.id, self.adapter)
        await engine.initialize()
        self.engines[sess.id] = engine
        asyncio.create_task(engine.run_loop())
        
        # Restore Real-time
        if hasattr(self.adapter, "start_realtime"):
             asyncio.create_task(self.adapter.start_realtime([sess.symbol]))

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

        # 0.5 Send Initial Strategy Status Immediately
        try:
            if hasattr(engine, 'strategy_instance') and hasattr(engine.strategy_instance, 'get_state'):
                init_state = engine.strategy_instance.get_state()
                if init_state:
                    await queue.put({
                        "type": "strategy_status",
                        "data": init_state
                    })
        except Exception as e:
            logger.error(f"Failed to send initial strategy status: {e}")
        
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
