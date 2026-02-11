
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
    Supports multiple accounts with separate adapters (Phase 1-2 Multi-Account).
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

        # Exclusive mode: per-account lock for multi-rank competition
        self._exclusive_groups: Dict[int, set] = {}          # account_id -> {session_ids}
        self._exclusive_lock: Dict[int, Optional[str]] = {}  # account_id -> locked_session_id

        # ── Phase 1: Multi-Account Adapter Pool ──
        # Each account has its own adapter with separate credentials and token
        self._adapters: Dict[int, KiwoomRealAdapter] = {}  # account_id -> adapter
        self._primary_account_id: Optional[int] = None  # For backward compatibility

        # Create a default adapter for initialization (will be replaced when account is selected)
        self._default_adapter = KiwoomRealAdapter()
        self._setup_adapter_listeners(self._default_adapter)

    @property
    def adapter(self) -> KiwoomRealAdapter:
        """Backward compatibility: returns the primary account's adapter or default."""
        if self._primary_account_id and self._primary_account_id in self._adapters:
            return self._adapters[self._primary_account_id]
        return self._default_adapter

    @adapter.setter
    def adapter(self, value: KiwoomRealAdapter):
        """Backward compatibility: sets the default adapter."""
        self._default_adapter = value

    def _setup_adapter_listeners(self, adapter: KiwoomRealAdapter = None):
        """Setup listeners on the specified adapter instance."""
        target = adapter or self.adapter
        # Register Global Tick Listener
        if hasattr(target, "add_tick_listener"):
            target.add_tick_listener(self._on_tick)
        # Register Order Fill Listener (체결 확인)
        if hasattr(target, "add_order_listener"):
            target.add_order_listener(self._on_order_fill)
        # Bind this adapter's callback to the singleton WebSocket
        # Must be called AFTER adding listeners so they are registered
        if hasattr(target, "setup_realtime_callbacks"):
            target.setup_realtime_callbacks()

    # ── Phase 1: Multi-Account Adapter Management ──

    async def get_or_create_adapter(self, account_id: int) -> KiwoomRealAdapter:
        """
        Get existing adapter for account or create a new one.
        Each account has its own adapter with separate credentials and token.
        """
        if account_id in self._adapters:
            return self._adapters[account_id]

        # Create new adapter for this account
        adapter = await self._create_adapter_for_account(account_id)
        if adapter:
            self._adapters[account_id] = adapter
            self._setup_adapter_listeners(adapter)
            logger.info(f"Created new adapter for account_id={account_id}")
            return adapter
        else:
            logger.error(f"Failed to create adapter for account_id={account_id}")
            raise ValueError(f"Cannot create adapter for account {account_id}")

    async def _create_adapter_for_account(self, account_id: int) -> Optional[KiwoomRealAdapter]:
        """Create a new KiwoomRealAdapter with credentials from DB."""
        from ..models.account import ExchangeAccount
        from ..core import security

        db = SessionLocal()
        try:
            account = db.query(ExchangeAccount).filter(
                ExchangeAccount.id == account_id
            ).first()

            if not account:
                logger.error(f"Account {account_id} not found in DB")
                return None

            try:
                decrypted_app = security.decrypt_key(account.encrypted_access_key)
                decrypted_secret = security.decrypt_key(account.encrypted_secret_key)

                adapter = KiwoomRealAdapter(
                    app_key=decrypted_app,
                    secret_key=decrypted_secret,
                    account_no=account.account_number,
                    account_name=account.account_name,
                    api_url=account.api_url,
                    is_virtual=account.is_virtual
                )
                logger.info(f"Adapter created for account '{account.account_name}' "
                           f"(virtual={account.is_virtual})")
                return adapter
            except Exception as e:
                logger.error(f"Failed to decrypt account keys for {account_id}: {e}")
                return None
        finally:
            db.close()

    def get_adapter_for_account(self, account_id: int) -> Optional[KiwoomRealAdapter]:
        """Get existing adapter for account (sync version, returns None if not exists)."""
        return self._adapters.get(account_id)

    def remove_adapter(self, account_id: int):
        """Remove adapter from pool (e.g., when account is deleted or all sessions stopped)."""
        if account_id in self._adapters:
            del self._adapters[account_id]
            logger.info(f"Removed adapter for account_id={account_id}")

    async def _reinitialize_adapter(self, account_id: int = None):
        """
        Reinitialize adapter with account credentials from DB.
        Now uses the adapter pool instead of replacing the single adapter.

        Args:
            account_id: Specific account ID to use. If None, uses the first active account.
        """
        from ..models.account import ExchangeAccount

        db = SessionLocal()
        try:
            if account_id:
                target_account_id = account_id
            else:
                # Fallback: first active account (legacy behavior)
                active_account = db.query(ExchangeAccount).filter(
                    ExchangeAccount.is_active == True
                ).first()
                target_account_id = active_account.id if active_account else None

            if not target_account_id:
                logger.warning("LiveManager: No active account found in DB. Using default adapter.")
                return False

            # Use the new adapter pool mechanism
            try:
                adapter = await self.get_or_create_adapter(target_account_id)
                self._primary_account_id = target_account_id
                logger.info(f"LiveManager: Primary adapter set to account_id={target_account_id}")
                return True
            except Exception as e:
                logger.error(f"Failed to create adapter for account {target_account_id}: {e}")
                return False
        finally:
            db.close()

    async def on_account_changed(self, account_id: int = None):
        """
        Called when the active account is changed in Settings.
        With multi-account support, this sets the PRIMARY account for new sessions.
        Existing sessions keep their original adapters (no longer switched).

        Args:
            account_id: The ID of the newly activated account.
        """
        logger.info(f"LiveManager: Account change detected (account_id={account_id}). Setting as primary...")

        if not account_id:
            return {"status": "error", "message": "account_id is required"}

        # Get or create adapter for this account
        try:
            adapter = await self.get_or_create_adapter(account_id)
            self._primary_account_id = account_id
        except Exception as e:
            logger.error(f"LiveManager: Failed to get adapter for account {account_id}: {e}")
            return {"status": "error", "message": f"Failed to initialize adapter: {e}"}

        # Acquire token for new adapter
        if hasattr(adapter, '_ensure_token'):
            try:
                await adapter._ensure_token()
                if adapter.access_token:
                    logger.info(f"LiveManager: Token acquired for account {account_id}.")
                else:
                    logger.warning(f"LiveManager: Failed to acquire token for account {account_id}.")
            except Exception as e:
                logger.error(f"LiveManager: Token acquisition failed for account {account_id}: {e}")

        # Update WebSocket URI and credentials for the primary adapter (only if WS exists)
        # Use _ws_client to avoid lazy creation - WS will be created when start_realtime is called
        if adapter._ws_client:
            ws = adapter._ws_client

            # Update URI
            if hasattr(ws, 'update_uri'):
                uri_changed = ws.update_uri(adapter.base_url)
                if uri_changed:
                    logger.info("LiveManager: WebSocket URI updated for account change")

            # Update credentials for token refresh (with new token)
            if hasattr(ws, 'update_credentials'):
                ws.update_credentials(
                    adapter.app_key,
                    adapter.secret_key,
                    adapter.access_token
                )

            # Force reconnect if WebSocket is running
            if ws.is_running:
                await ws._force_reconnect()

        # NOTE: With multi-account support, we NO LONGER update existing engines' adapters.
        # Each session keeps its original adapter. Only log how many sessions exist for each account.
        sessions_by_account: Dict[int, int] = {}
        for session_id, engine in self.engines.items():
            # Determine account_id from DB
            db = SessionLocal()
            try:
                sess = db.query(LiveBotSession).filter_by(id=session_id).first()
                if sess:
                    acc_id = sess.account_id
                    sessions_by_account[acc_id] = sessions_by_account.get(acc_id, 0) + 1
            finally:
                db.close()

        if sessions_by_account:
            logger.info(f"LiveManager: Active sessions by account: {sessions_by_account}")

        return {
            "status": "success",
            "message": f"Primary account set to {adapter.get_name()}",
            "account_name": adapter.get_account_name(),
            "is_virtual": adapter.is_virtual,
            "active_sessions_by_account": sessions_by_account
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
        Phase 2: Now restores sessions from ALL accounts with separate adapters.
        """
        # Connect to MarketRouter
        market_data_router.set_live_manager(self)

        db = SessionLocal()
        try:
            # 1. Get all RUNNING sessions and group by account_id
            active_sessions = db.query(LiveBotSession).filter(
                LiveBotSession.status == SessionStatus.RUNNING
            ).all()

            if not active_sessions:
                logger.info("LiveManager: No RUNNING sessions to restore.")
                # Still initialize adapter with first active account for API calls
                await self._reinitialize_adapter()
                return

            # 2. Group sessions by account_id
            sessions_by_account: Dict[int, List] = {}
            for sess in active_sessions:
                acc_id = sess.account_id
                if acc_id not in sessions_by_account:
                    sessions_by_account[acc_id] = []
                sessions_by_account[acc_id].append(sess)

            logger.info(f"LiveManager: Found {len(active_sessions)} RUNNING sessions across "
                       f"{len(sessions_by_account)} accounts")

            # 3. Set primary account (the one with most sessions, for backward compat)
            primary_account_id = max(sessions_by_account.keys(),
                                     key=lambda k: len(sessions_by_account[k]))
            self._primary_account_id = primary_account_id

            # 4. Phase 2: Restore sessions from ALL accounts (no longer ERROR for other accounts)
            restored_ids = set()
            for acc_id, sessions in sessions_by_account.items():
                logger.info(f"LiveManager: Restoring {len(sessions)} sessions for account_id={acc_id}")

                # Create adapter for this account and acquire token
                try:
                    adapter = await self.get_or_create_adapter(acc_id)

                    # Ensure token is ready for this account
                    if hasattr(adapter, '_ensure_token'):
                        logger.info(f"LiveManager: Acquiring token for account {acc_id}...")
                        for attempt in range(3):
                            try:
                                await adapter._ensure_token()
                                if adapter.access_token:
                                    logger.info(f"LiveManager: Token acquired for account {acc_id}.")
                                    break
                            except Exception as e:
                                logger.warning(f"Token attempt {attempt + 1} for account {acc_id} failed: {e}")
                            await asyncio.sleep(2)
                        else:
                            logger.error(f"LiveManager: Failed to acquire token for account {acc_id} after 3 attempts.")
                except Exception as e:
                    logger.error(f"Failed to create adapter for account {acc_id}: {e}")
                    # Mark all sessions for this account as ERROR
                    for sess in sessions:
                        sess.status = SessionStatus.ERROR
                        sess.error_log = f"Failed to create adapter: {e}"
                    db.commit()
                    continue

                # Restore each session for this account
                for sess in sessions:
                    try:
                        logger.info(f"Restoring Live Session: {sess.id} ({sess.symbol}) [account={acc_id}]")
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
                            context={"strategy_name": sess.strategy_name, "account_id": acc_id}
                        )
                        sess.status = SessionStatus.ERROR
                        sess.error_log = str(e)
                        db.commit()

            # NOTE: Auto-Start logic removed in v0.9.7.3 due to duplicate key errors
            # and conflicts with existing RUNNING sessions. Users must manually start strategies.

            # 5. Reconstruct exclusive groups from ALL restored sessions
            for acc_id, sessions in sessions_by_account.items():
                for sess in sessions:
                    if sess.id not in restored_ids:
                        continue
                    cfg = sess.strategy_config or {}
                    if cfg.get("execution_mode") == "exclusive":
                        self.register_exclusive_session(sess.account_id, sess.id)
                        # If session has open position, it holds the exclusive lock
                        pos = self._check_session_position(sess.id)
                        if pos:
                            self._exclusive_lock[sess.account_id] = sess.id
                            logger.info(f"Exclusive lock restored to session {sess.id} (has position: {pos['symbol']} L{pos['level']})")

            logger.info(f"LiveManager: Initialization complete. Restored {len(restored_ids)} sessions, "
                       f"{len(self._adapters)} adapters active.")

        finally:
            db.close()

    async def start_session(self, config: Dict[str, Any]) -> str:
        """
        Create and optionally Start a new Live Session.
        config: {
            "symbol": str,
            "strategy_name": str,
            "strategy_config": dict,
            "initial_capital": float,
            "auto_start": bool (default: False) - if False, creates session in STOPPED state
        }
        """
        session_id = config.get("session_id") or str(uuid.uuid4())
        symbol = config.get("symbol")
        strategy_name = config.get("strategy_name", "time_momentum")
        strat_config = config.get("strategy_config", {})
        initial_capital = config.get("initial_capital", 0)
        is_paper = config.get("is_paper", True)
        account_id = config.get("account_id")  # 계좌 ID 필수
        group_id = config.get("group_id")  # 세션 그룹 ID (optional)
        profile_name = config.get("profile_name")  # 프로필 이름 (optional)
        auto_start = config.get("auto_start", False)  # 자동 시작 여부 (기본: False)

        if not account_id:
            raise ValueError("account_id is required to start a live session")

        # 1. DB Record - status depends on auto_start
        initial_status = SessionStatus.RUNNING if auto_start else SessionStatus.STOPPED
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
                status=initial_status,
                started_at=datetime.now() if auto_start else None,
                interval="1m", # Default to 1m for now
                group_id=group_id,  # 세션 그룹 ID
                profile_name=profile_name  # 프로필 이름
            )
            db.add(sess)
            db.commit()
        except Exception as e:
            db.close()
            raise e

        # If auto_start is False, just return session_id without starting engine
        if not auto_start:
            logger.info(f"Created Live Session {session_id} in STOPPED state (auto_start=False)")
            db.close()
            return session_id

        # 2. Engine Create & Start (only if auto_start=True)
        try:
            # Phase 2: Use account-specific adapter
            adapter = await self.get_or_create_adapter(account_id)

            # Ensure token is ready for this account
            if hasattr(adapter, '_ensure_token'):
                await adapter._ensure_token()

            # Note: Strategy class resolution moved inside LiveTradingEngine.initialize()
            engine = LiveTradingEngine(session_id, adapter)
            await engine.initialize()

            self.engines[session_id] = engine
            asyncio.create_task(engine.run_loop())

            # Register in exclusive group if applicable
            execution_mode = strat_config.get("execution_mode")
            if execution_mode == "exclusive":
                self.register_exclusive_session(account_id, session_id)

            # Start Real-time Data Stream for this symbol (using this account's adapter)
            if hasattr(adapter, "start_realtime"):
                asyncio.create_task(adapter.start_realtime([symbol]))

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

    def _check_session_position(self, session_id: str) -> dict:
        """Check if a running session has an open position. Returns position info or None."""
        engine = self.engines.get(session_id)
        if not engine or not engine.strategy_instance:
            return None
        try:
            state = engine.strategy_instance.get_state()
            total_qty = state.get("total_quantity", 0)
            if total_qty > 0:
                return {
                    "symbol": state.get("symbol", engine.symbol),
                    "level": state.get("current_level", 0),
                    "total_quantity": total_qty,
                    "average_price": state.get("average_price", 0),
                }
        except Exception as e:
            logger.warning(f"Failed to check position for {session_id}: {e}")
        return None

    # ── Exclusive Mode Lock Management ──

    def register_exclusive_session(self, account_id: int, session_id: str):
        """Register a session as part of an exclusive competition group."""
        if account_id not in self._exclusive_groups:
            self._exclusive_groups[account_id] = set()
            self._exclusive_lock[account_id] = None
        self._exclusive_groups[account_id].add(session_id)
        logger.info(f"Exclusive group [{account_id}]: registered {session_id} "
                    f"(total: {len(self._exclusive_groups[account_id])})")

    def unregister_exclusive_session(self, account_id: int, session_id: str):
        """Remove a session from its exclusive group and release lock if held."""
        if account_id in self._exclusive_groups:
            self._exclusive_groups[account_id].discard(session_id)
            if self._exclusive_lock.get(account_id) == session_id:
                self._exclusive_lock[account_id] = None
                logger.info(f"Exclusive lock released (session removed): {session_id}")
            if not self._exclusive_groups[account_id]:
                del self._exclusive_groups[account_id]
                self._exclusive_lock.pop(account_id, None)

    def try_acquire_exclusive_lock(self, account_id: int, session_id: str) -> bool:
        """Try to acquire the exclusive trading lock. Returns True if acquired or already held."""
        if account_id not in self._exclusive_lock:
            return True  # Not in an exclusive group
        current = self._exclusive_lock[account_id]
        if current is None:
            self._exclusive_lock[account_id] = session_id
            logger.info(f"Exclusive lock ACQUIRED by session {session_id}")
            return True
        return current == session_id  # Same session can buy again (L2+ entries)

    def release_exclusive_lock(self, account_id: int, session_id: str):
        """Release the exclusive lock if held by this session (cycle completed)."""
        if account_id in self._exclusive_lock and self._exclusive_lock[account_id] == session_id:
            self._exclusive_lock[account_id] = None
            logger.info(f"Exclusive lock RELEASED by session {session_id} (cycle completed)")

    def get_exclusive_holder(self, account_id: int) -> Optional[str]:
        """Get the session_id that currently holds the exclusive lock, or None."""
        return self._exclusive_lock.get(account_id)

    async def stop_session(self, session_id: str, force: bool = False):
        # Block stop when holding position (unless force from START flow)
        if not force:
            pos = self._check_session_position(session_id)
            if pos:
                raise ValueError(
                    f"POSITION_HELD|{pos['symbol']} L{pos['level']} {pos['total_quantity']:.0f}주"
                )

        if session_id in self.engines:
            logger.info(f"Stopping Live Session {session_id}...")
            engine = self.engines[session_id]
            engine.stop()
            del self.engines[session_id]

        # Update DB & unregister from exclusive group
        db = SessionLocal()
        try:
            sess = db.query(LiveBotSession).filter_by(id=session_id).first()
            if sess:
                sess.status = SessionStatus.STOPPED
                sess.is_active = False # Deactivate so it's not restored
                sess.stopped_at = datetime.now()
                db.commit()
                # Unregister from exclusive group
                cfg = sess.strategy_config or {}
                if cfg.get("execution_mode") == "exclusive":
                    self.unregister_exclusive_session(sess.account_id, session_id)
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
        Force Close Position: Market sell all holdings.
        Does NOT disable orders - use toggle_orders() separately for that.
        """
        if session_id in self.engines:
            await self.engines[session_id].liquidate_all()
            logger.info(f"Session {session_id}: Force-closed all positions.")

    async def get_status(self, session_id: str = None, account_id: int = None, account_ids: List[int] = None) -> List[Dict]:
        """
        Return status of specific session or all managed sessions.

        Args:
            session_id: Return only this specific session
            account_id: Filter sessions by single account
            account_ids: Phase 5 - Filter sessions by multiple accounts (for Session Switcher)
        """
        results = []

        # Determine targets based on session_id or filter by account_id(s)
        if session_id:
            targets = [session_id]
        elif account_ids is not None:
            # Phase 5: Filter by multiple account IDs (Session Switcher)
            db = SessionLocal()
            try:
                sessions = db.query(LiveBotSession).filter(
                    LiveBotSession.account_id.in_(account_ids),
                    LiveBotSession.is_active == True
                ).all()
                targets = [s.id for s in sessions if s.id in self.engines]
            finally:
                db.close()
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
                    # Use the engine's adapter (account-specific)
                    price_data = await eng.adapter.get_current_price(eng.symbol)
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
                "trade_stats": trade_stats,
                # Phase 5: Multi-account fields for Session Switcher
                "account_id": getattr(eng, '_account_id', None),
                "initial_capital": getattr(eng.context, 'initial_capital', 0)
            })
        return results

    async def _restore_engine(self, sess: LiveBotSession):
        """Restore a single session with its account-specific adapter."""
        # Phase 2: Use account-specific adapter
        adapter = await self.get_or_create_adapter(sess.account_id)

        engine = LiveTradingEngine(sess.id, adapter)
        await engine.initialize()
        self.engines[sess.id] = engine
        asyncio.create_task(engine.run_loop())

        # Restore Real-time using this session's adapter
        if hasattr(adapter, "start_realtime"):
            asyncio.create_task(adapter.start_realtime([sess.symbol]))

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

    async def stop_all_sessions_for_account(self, account_id: int, force: bool = False) -> int:
        """
        Stop all RUNNING sessions for a specific account.
        Returns the number of sessions stopped.
        Used before starting new sessions to prevent duplicates.
        force=True: bypass position check (used by START flow to clean up old sessions)
        force=False: respect position check (used by STOP button)
        """
        db = SessionLocal()
        stopped_count = 0
        try:
            # Find all RUNNING sessions for this account
            running_sessions = db.query(LiveBotSession).filter(
                LiveBotSession.account_id == account_id,
                LiveBotSession.status == SessionStatus.RUNNING
            ).all()

            for sess in running_sessions:
                try:
                    await self.stop_session(sess.id, force=force)
                    stopped_count += 1
                    logger.info(f"Stopped existing session {sess.id} (symbol: {sess.symbol}) for account {account_id}")
                except ValueError:
                    # Re-raise position check errors (only when force=False)
                    raise
                except Exception as e:
                    logger.error(f"Failed to stop session {sess.id}: {e}")
                    # Mark as ERROR in DB if stop failed
                    sess.status = SessionStatus.ERROR
                    sess.error_log = f"Failed to stop: {e}"
                    db.commit()

            return stopped_count
        finally:
            db.close()

    async def cleanup_for_logout(self, user_id: int):
        """
        Clean up all state for user logout.
        Called after verifying no live sessions are running.
        """
        from ..core.account_cache import AccountCache
        from ..core.token_manager import KiwoomTokenManager

        # 1. Clear account cache
        cache = AccountCache.get_instance()
        cache.invalidate(user_id)
        logger.info(f"Account cache cleared for user {user_id}")

        # 2. Clear all Kiwoom tokens
        token_manager = KiwoomTokenManager.get_instance()
        token_manager.clear_all()
        logger.info("Kiwoom tokens cleared")

        # 3. Clear WebSocket monitored symbols for all adapters (Phase 4)
        # Use _ws_client to avoid lazy creation of new WebSocket instances
        for account_id, adapter in self._adapters.items():
            if adapter._ws_client:
                adapter._ws_client.clear_symbols()
        logger.info(f"WebSocket symbols cleared for {len(self._adapters)} adapters")

        # 4. Clear MarketDataRouter
        market_data_router.clear_all()
        logger.info("MarketDataRouter cleared")

        return {"status": "success", "message": "Logout cleanup completed"}

    async def stop_all_websockets(self):
        """
        Stop all WebSocket connections for all adapters.
        Called on application shutdown (Phase 4).
        Use _ws_client to avoid lazy creation of new WebSocket instances.
        """
        stopped_count = 0
        for account_id, adapter in self._adapters.items():
            if adapter._ws_client:
                ws = adapter._ws_client
                ws.is_running = False
                if ws.websocket and not ws.websocket.closed:
                    try:
                        await ws.websocket.close()
                        stopped_count += 1
                    except Exception as e:
                        logger.error(f"Error closing WS for account {account_id}: {e}")
        logger.info(f"WS: Closed {stopped_count} connections on shutdown")


# Global Access
live_manager = LiveManager.get_instance()
