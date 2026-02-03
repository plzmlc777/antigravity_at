
import asyncio
import logging
import uuid
import traceback
from typing import Dict, Any, List, Optional
from datetime import datetime

from ..core.live_engine import LiveTradingEngine
from ..adapters.kiwoom_real import KiwoomRealAdapter
from ..core.config import settings
from ..db.session import SessionLocal
from ..models.live_trading import LiveBotSession, SessionStatus, ErrorType, ErrorSeverity
from ..models.strategy_config import StrategyConfig
from ..core.market_data_router import market_data_router
from ..services.error_logger import error_logger

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
        # Track pending orders: order_no -> {session_id, db_execution_id, ...}
        self.pending_orders: Dict[str, Dict[str, Any]] = {}

        # Always use KiwoomRealAdapter (paper/real trading controlled by session's is_paper flag)
        # Initially created without credentials; will be reinitialized in initialize() with DB account
        self.adapter = KiwoomRealAdapter()
        self._setup_adapter_listeners()

    def _setup_adapter_listeners(self):
        """Setup listeners on the current adapter instance."""
        # Register Global Tick Listener
        if hasattr(self.adapter, "add_tick_listener"):
            self.adapter.add_tick_listener(self._on_tick)
        # Register Order Fill Listener (체결 확인)
        if hasattr(self.adapter, "add_order_listener"):
            self.adapter.add_order_listener(self._on_order_fill)
        # Bind this adapter's callback to the singleton WebSocket
        # Must be called AFTER adding listeners so they are registered
        if hasattr(self.adapter, "setup_realtime_callbacks"):
            self.adapter.setup_realtime_callbacks()

    async def _reinitialize_adapter(self):
        """
        Reinitialize adapter with active account credentials from DB.
        Called during initialize() to get proper credentials for token acquisition.
        """
        from ..models.account import ExchangeAccount
        from ..core import security

        db = SessionLocal()
        try:
            active_account = db.query(ExchangeAccount).filter(
                ExchangeAccount.is_active == True
            ).first()

            if active_account:
                try:
                    decrypted_app = security.decrypt_key(active_account.encrypted_access_key)
                    decrypted_secret = security.decrypt_key(active_account.encrypted_secret_key)

                    # Create new adapter with DB credentials
                    self.adapter = KiwoomRealAdapter(
                        app_key=decrypted_app,
                        secret_key=decrypted_secret,
                        account_no=active_account.account_number,
                        account_name=active_account.account_name,
                        api_url=active_account.api_url,
                        is_virtual=active_account.is_virtual
                    )
                    self._setup_adapter_listeners()
                    logger.info(f"LiveManager: Adapter reinitialized with account '{active_account.account_name}' "
                               f"(virtual={active_account.is_virtual}, url={active_account.api_url or 'default'})")
                    return True
                except Exception as e:
                    logger.error(f"Failed to decrypt account keys: {e}")
                    return False
            else:
                logger.warning("LiveManager: No active account found in DB. Using default adapter.")
                return False
        finally:
            db.close()

    async def on_account_changed(self):
        """
        Called when the active account is changed in Settings.
        Reinitializes the adapter, WebSocket, and acquires a new token.
        """
        logger.info("LiveManager: Account change detected. Reinitializing adapter...")

        # Reinitialize adapter with new account
        success = await self._reinitialize_adapter()
        if not success:
            logger.error("LiveManager: Failed to reinitialize adapter on account change.")
            return {"status": "error", "message": "Failed to reinitialize adapter"}

        # Acquire token for new adapter FIRST (before updating WebSocket)
        if hasattr(self.adapter, '_ensure_token'):
            try:
                await self.adapter._ensure_token()
                if self.adapter.access_token:
                    logger.info("LiveManager: Token acquired for new account.")
                else:
                    logger.warning("LiveManager: Failed to acquire token for new account.")
            except Exception as e:
                logger.error(f"LiveManager: Token acquisition failed: {e}")

        # Update WebSocket URI and credentials to match new account
        if hasattr(self.adapter, 'ws_client'):
            ws = self.adapter.ws_client

            # Update URI
            if hasattr(ws, 'update_uri'):
                uri_changed = ws.update_uri(self.adapter.base_url)
                if uri_changed:
                    logger.info("LiveManager: WebSocket URI updated for account change")

            # Update credentials for token refresh (with new token)
            if hasattr(ws, 'update_credentials'):
                ws.update_credentials(
                    self.adapter.app_key,
                    self.adapter.secret_key,
                    self.adapter.access_token
                )

            # Force reconnect if WebSocket is running
            if ws.is_running:
                await ws._force_reconnect()

        # Update all running engines with new adapter reference
        for session_id, engine in self.engines.items():
            engine.adapter = self.adapter
            logger.info(f"LiveManager: Updated adapter for session {session_id}")

        return {
            "status": "success",
            "message": f"Adapter switched to {self.adapter.get_name()}",
            "account_name": self.adapter.get_account_name(),
            "is_virtual": self.adapter.is_virtual
        }

    def _on_tick(self, tick_data: Dict):
        """
        Route global tick to specific engine
        """
        symbol = tick_data.get("symbol")
        if not symbol: return

        for engine in self.engines.values():
            if engine.symbol == symbol:
                asyncio.create_task(engine.process_realtime_tick(tick_data))

    def _on_order_fill(self, order_data: Dict):
        """
        Handle order execution notification from WebSocket.
        Updates DB with actual fill price/quantity.
        """
        try:
            order_no = order_data.get("order_no")
            filled_qty = order_data.get("filled_qty", 0)
            exec_price = order_data.get("exec_price", 0)
            symbol = order_data.get("symbol")

            # 체결 수량이 있는 경우만 처리 (접수 이벤트 무시)
            if not filled_qty or filled_qty <= 0:
                return

            logger.info(f"Order Fill Received: order_no={order_no}, symbol={symbol}, "
                       f"qty={filled_qty}, price={exec_price}")

            # Find and update the execution in DB
            asyncio.create_task(self._update_execution_fill(order_no, order_data))

        except Exception as e:
            logger.error(f"Error handling order fill: {e}", exc_info=True)
            error_logger.log_order_error(
                message=f"Error handling order fill: {e}",
                session_id=None,
                symbol=order_data.get("symbol") if order_data else None,
                exception=e,
                context=order_data
            )

    async def _update_execution_fill(self, order_no: str, order_data: Dict):
        """
        Update LiveTradeExecution with actual fill data from WebSocket.
        Matches by Kiwoom order_no (exchange_order_no) stored during order placement.
        """
        from ..models.live_trading import LiveTradeExecution, ExecutionStatus

        db = SessionLocal()
        try:
            symbol = order_data.get("symbol")
            filled_qty = order_data.get("filled_qty", 0)
            exec_price = order_data.get("exec_price", 0)

            execution = None

            # 1. First try: Match by exchange_order_no (가장 정확)
            if order_no:
                execution = db.query(LiveTradeExecution).filter(
                    LiveTradeExecution.exchange_order_no == order_no,
                    LiveTradeExecution.status == ExecutionStatus.FILLED,
                ).first()

                if execution:
                    logger.debug(f"Matched by exchange_order_no: {order_no}")

            # 2. Fallback: Match by symbol + quantity + pending update
            if not execution:
                executions = db.query(LiveTradeExecution).filter(
                    LiveTradeExecution.symbol == symbol,
                    LiveTradeExecution.status == ExecutionStatus.FILLED,
                    LiveTradeExecution.is_paper == False,  # Real 모드만
                    LiveTradeExecution.executed_price == LiveTradeExecution.theoretical_price  # 아직 업데이트 안됨
                ).order_by(LiveTradeExecution.order_filled_at.desc()).limit(5).all()

                for ex in executions:
                    if ex.filled_quantity == filled_qty or ex.requested_quantity == filled_qty:
                        execution = ex
                        logger.debug(f"Matched by symbol+quantity fallback: {symbol}, qty={filled_qty}")
                        break

            if not execution:
                logger.debug(f"No pending execution found for order_no={order_no}, symbol={symbol}")
                return

            # 3. Update execution with actual fill data
            old_price = execution.executed_price
            execution.executed_price = exec_price
            execution.slippage = round(exec_price - execution.theoretical_price, 2)
            execution.slippage_percent = round(
                (execution.slippage / execution.theoretical_price) * 100, 4
            ) if execution.theoretical_price else 0

            # 4. Recalculate realized_pnl for SELL orders
            if execution.signal_type == "SELL":
                buys = db.query(LiveTradeExecution).filter(
                    LiveTradeExecution.session_id == execution.session_id,
                    LiveTradeExecution.symbol == execution.symbol,
                    LiveTradeExecution.signal_type == "BUY",
                    LiveTradeExecution.status == ExecutionStatus.FILLED,
                ).all()
                total_buy_cost = sum((b.executed_price or 0) * (b.filled_quantity or 0) for b in buys)
                total_buy_qty = sum(b.filled_quantity or 0 for b in buys)
                if total_buy_qty > 0:
                    avg_buy_price = total_buy_cost / total_buy_qty
                    execution.realized_pnl = round(
                        (execution.executed_price - avg_buy_price) * execution.filled_quantity, 2
                    )

            db.commit()
            logger.info(f"✓ Execution Fill Updated: {execution.signal_type} {symbol} "
                       f"price {old_price:,.0f} → {exec_price:,.0f} (slippage: {execution.slippage:+,.0f})")

        except Exception as e:
            logger.error(f"Error updating execution fill: {e}", exc_info=True)
            error_logger.log_error(
                error_type=ErrorType.DB_ERROR,
                message=f"Error updating execution fill: {e}",
                symbol=symbol,
                exception=e,
                context={"order_no": order_no, "order_data": order_data},
                source_function="_update_execution_fill"
            )
            db.rollback()
        finally:
            db.close()
        
    async def initialize(self):
        """
        Load active sessions from DB on server startup.
        """
        # Connect to MarketRouter
        market_data_router.set_live_manager(self)

        # Reinitialize adapter with active account credentials from DB
        await self._reinitialize_adapter()

        # Update WebSocket URI to match active account's api_url
        if hasattr(self.adapter, 'ws_client') and hasattr(self.adapter.ws_client, 'update_uri'):
            self.adapter.ws_client.update_uri(self.adapter.base_url)
            logger.info(f"LiveManager: WebSocket URI set to match account api_url: {self.adapter.base_url}")

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
                    error_logger.log_critical(
                        error_type=ErrorType.SYSTEM_ERROR,
                        message=f"Failed to restore session: {e}",
                        session_id=sess.id,
                        symbol=sess.symbol,
                        exception=e,
                        context={"strategy_name": sess.strategy_name}
                    )
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
        account_id = config.get("account_id")  # 계좌 ID 필수

        if not account_id:
            raise ValueError("account_id is required to start a live session")

        # 1. DB Record
        db = SessionLocal()
        try:
            sess = LiveBotSession(
                id=session_id,
                account_id=account_id,  # 계좌 ID 저장
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

    async def get_status(self, session_id: str = None, account_id: int = None) -> List[Dict]:
        """
        Return status of specific session or all managed sessions.
        If account_id is provided, filter sessions by that account.
        """
        results = []

        # Determine targets based on session_id or filter by account_id
        if session_id:
            targets = [session_id]
        elif account_id is not None:
            # Filter sessions by account_id from DB
            db = SessionLocal()
            try:
                sessions = db.query(LiveBotSession).filter(
                    LiveBotSession.account_id == account_id,
                    LiveBotSession.is_active == True
                ).all()
                targets = [s.id for s in sessions if s.id in self.engines]
            finally:
                db.close()
        else:
            targets = list(self.engines.keys())

        for sid in targets:
            if sid not in self.engines: continue
            eng = self.engines[sid]

            # Get current price - fallback to API if price_map is empty
            current_price = eng.context.get_current_price(eng.symbol)
            if current_price == 0:
                try:
                    price_data = await self.adapter.get_current_price(eng.symbol)
                    current_price = price_data.get('price', 0)
                    # Update price_map for future calls
                    if current_price > 0:
                        eng.context.price_map[eng.symbol] = current_price
                except Exception as e:
                    logger.warning(f"Failed to fetch price for {eng.symbol}: {e}")

            # Context Summary (Isolated PnL based on trades)
            pnl = eng.context.calculate_pnl()

            strategy_state = {}
            try:
                if hasattr(eng, 'strategy_instance') and hasattr(eng.strategy_instance, 'get_state'):
                    strategy_state = eng.strategy_instance.get_state()
            except Exception:
                pass

            trade_stats = {}
            try:
                trade_stats = eng.context.get_trade_stats()
            except Exception:
                pass

            results.append({
                "session_id": sid,
                "symbol": eng.symbol,
                "strategy_name": getattr(eng, 'strategy_name', 'unknown'),
                "is_running": eng.is_running,
                "orders_enabled": eng.orders_enabled,
                "is_paper": getattr(eng, 'is_paper', True),
                "current_price": current_price,
                "pnl": pnl,
                "trades_count": len(eng.context.trades),
                "last_update": datetime.now().isoformat(),
                "strategy_state": strategy_state,
                "trade_stats": trade_stats
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

    def get_active_sessions_count(self) -> int:
        """Return count of currently running sessions"""
        return len(self.engines)

    def get_active_session_ids(self) -> List[str]:
        """Return list of active session IDs"""
        return list(self.engines.keys())

    async def stop_all_sessions(self):
        """Stop all running sessions (for logout/shutdown)"""
        session_ids = list(self.engines.keys())
        for session_id in session_ids:
            try:
                await self.stop_session(session_id)
                logger.info(f"Stopped session {session_id}")
            except Exception as e:
                logger.error(f"Failed to stop session {session_id}: {e}")

    async def cleanup_for_logout(self, user_id: int):
        """
        Clean up all state for user logout.
        Called after verifying no live sessions are running.
        """
        from ..core.account_cache import AccountCache
        from ..core.token_manager import KiwoomTokenManager
        from ..adapters.kiwoom_websocket import KiwoomWebSocket

        # 1. Clear account cache
        cache = AccountCache.get_instance()
        cache.invalidate(user_id)
        logger.info(f"Account cache cleared for user {user_id}")

        # 2. Clear all Kiwoom tokens
        token_manager = KiwoomTokenManager.get_instance()
        token_manager.clear_all()
        logger.info("Kiwoom tokens cleared")

        # 3. Clear WebSocket monitored symbols and stop
        ws = KiwoomWebSocket.get_instance()
        ws.clear_symbols()
        logger.info("WebSocket symbols cleared")

        # 4. Clear MarketDataRouter
        market_data_router.clear_all()
        logger.info("MarketDataRouter cleared")

        return {"status": "success", "message": "Logout cleanup completed"}


# Global Access
live_manager = LiveManager.get_instance()
