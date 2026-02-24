
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
import asyncio
import logging
import re
import traceback
from sqlalchemy.orm import Session
from ..db.session import SessionLocal
from ..models.live_trading import LiveTradeExecution, LiveBotSession, ExecutionStatus, ErrorType, SessionStatus
from ..models.new_orders import StockOrder, OrderSide, OrderType
from ..core.exchange_interface import ExchangeInterface
from ..core.futures_interface import FuturesInterface
from ..services.error_logger import error_logger

logger = logging.getLogger(__name__)

class LiveContext:
    """
    Context for Live Trading Strategies.
    Mimics BacktestContext interface but executes against Real Adapter & DB.
    """
    def __init__(self, session_id: str, adapter: ExchangeInterface, initial_capital: float = 0.0, is_paper: bool = True, user_id: int = None, strategy_name: str = None, account_id: int = None):
        self.session_id = session_id
        self.adapter = adapter
        self.initial_capital = initial_capital
        self._is_paper = is_paper
        self._user_id = user_id  # For telegram notifications
        self._strategy_name = strategy_name  # For telegram notifications
        self._account_id = account_id  # For telegram notifications (per-account settings)

        # State
        self.cash = initial_capital
        self._holdings = {} # {symbol: quantity} (Synced with Adapter)
        self.trades = [] # Keep local copy for strategy logic
        self.logs = []
        self.equity_curve = []

        # Real-time Price Cache (Updated by Engine)
        self.price_map = {} # {symbol: price}

        # Strategy Config Snapshot (for parameter versioning)
        self._config_snapshot = None  # Set by engine before strategy execution

        # Exclusive mode gate: returns True if this session can buy, False if locked by another
        self._exclusive_gate: Optional[Callable[[], bool]] = None

        # Order fill callbacks: {order_id: callback_fn}
        # Callback is invoked after order is FILLED with (order_id, filled_qty, filled_price, metadata)
        self._order_callbacks: Dict[str, Callable] = {}

        # Futures data cache (updated by LiveEngine for FuturesInterface adapters)
        self._futures_data_cache: Dict[str, Dict[str, Any]] = {}

        # Initial Balance Sync
        self._sync_balance()

        # Restore trades from DB (for session recovery after restart)
        self._restore_trades_from_db()

    def get_current_price(self, symbol: str) -> float:
        """
        Returns latest price from cache. 
        Engine MUST update price_map before strategy runs.
        """
        return self.price_map.get(symbol, 0.0)

    def get_time(self) -> datetime:
        """Returns current real server time"""
        return datetime.now()

    @property
    def is_paper(self) -> bool:
        return self._is_paper

    @is_paper.setter
    def is_paper(self, value: bool):
        self._is_paper = value
        logger.info(f"Context {self.session_id}: Mode switched to {'PAPER' if value else 'REAL'}")

    def set_config_snapshot(self, config: Dict[str, Any], strategy_id: str = None, symbol: str = None):
        """
        Set the current strategy config snapshot for parameter versioning.
        Called by LiveEngine before each strategy tick.
        """
        self._config_snapshot = {
            "strategy_id": strategy_id,
            "symbol": symbol,
            "params": config,
            "snapshot_at": datetime.now().isoformat()
        }

    def get_futures_data(self, symbol: str) -> Dict[str, Any]:
        """
        Get cached futures data for a symbol.
        Updated periodically by LiveEngine for FuturesInterface adapters.
        Returns empty dict for spot adapters.
        """
        return self._futures_data_cache.get(symbol, {})

    def update_futures_data(self, symbol: str, data: Dict[str, Any]):
        """
        Update futures data cache. Called by LiveEngine._refresh_futures_data().
        Data includes: funding_rate, liquidation_price, mark_price, leverage,
        unrealized_pnl, position_side, position_qty, entry_price, adl_quantile
        """
        self._futures_data_cache[symbol] = data

    def get_total_equity(self) -> float:
        """
        Calculates total equity: Cash + Sum of (Holding Qty * Current Price)
        Uses price_map for latest known prices.
        """
        equity = self.cash
        for symbol, qty in self.holdings.items():
            price = self.price_map.get(symbol, 0.0)
            equity += qty * price
        return equity

    def calculate_pnl(self) -> float:
        """
        Calculates PnL based ONLY on trades executed during this session.
        PnL = Sum of (Sold Value) - Sum of (Bought Value) + (Current Holding Value)
        """
        db = SessionLocal()
        try:
            executions = db.query(LiveTradeExecution).filter(
                LiveTradeExecution.session_id == self.session_id,
                LiveTradeExecution.status == ExecutionStatus.FILLED
            ).all()
            
            total_bought_cost = 0.0
            total_sold_value = 0.0
            current_qty = 0.0
            
            for ex in executions:
                val = (ex.executed_price or 0.0) * (ex.filled_quantity or 0.0)
                if ex.signal_type == "BUY":
                    total_bought_cost += val
                    current_qty += (ex.filled_quantity or 0.0)
                elif ex.signal_type == "SELL":
                    total_sold_value += val
                    current_qty -= (ex.filled_quantity or 0.0)
            
            # Unrealized part of current holding
            current_price = self.get_current_price(executions[0].symbol if executions else "")

            # If current_price is 0 (market closed/unavailable), use average purchase price
            # This prevents showing large negative PnL when price data is unavailable
            if current_price == 0 and current_qty > 0 and total_bought_cost > 0:
                # Calculate average purchase price from remaining holdings
                total_bought_qty = sum(
                    (ex.filled_quantity or 0.0) for ex in executions if ex.signal_type == "BUY"
                )
                if total_bought_qty > 0:
                    avg_price = total_bought_cost / total_bought_qty
                    current_price = avg_price

            unrealized_value = current_qty * current_price

            return total_sold_value + unrealized_value - total_bought_cost
            
        except Exception as e:
            logger.error(f"PnL Calculation Error: {e}")
            error_logger.log_error(
                error_type=ErrorType.DB_ERROR,
                message=f"PnL Calculation Error: {e}",
                session_id=self.session_id,
                exception=e,
                source_function="calculate_pnl"
            )
            return 0.0
        finally:
            db.close()

    def get_trade_stats(self) -> Dict[str, Any]:
        """
        Compute accumulated trade stats separated by Paper/Real.
        Tracks per-cycle PnL for win_rate, max_pnl, min_pnl, recent_10_win_rate.
        """
        db = SessionLocal()
        try:
            executions = db.query(LiveTradeExecution).filter(
                LiveTradeExecution.session_id == self.session_id,
                LiveTradeExecution.status == ExecutionStatus.FILLED
            ).order_by(LiveTradeExecution.signal_timestamp).all()

            stats = {
                "paper": {"trades": 0, "buys": 0, "sells": 0, "cycles": 0, "realized_pnl": 0.0},
                "real": {"trades": 0, "buys": 0, "sells": 0, "cycles": 0, "realized_pnl": 0.0},
            }

            # Track running buy cost/qty per mode for per-cycle PnL
            running_buy_cost = {"paper": 0.0, "real": 0.0}
            running_buy_qty = {"paper": 0.0, "real": 0.0}
            # Per-cycle PnL list for win_rate, max, min
            cycle_pnls = {"paper": [], "real": []}

            for ex in executions:
                is_paper = ex.is_paper if ex.is_paper is not None else True
                key = "paper" if is_paper else "real"
                s = stats[key]
                s["trades"] += 1
                qty = ex.filled_quantity or 0.0
                val = (ex.executed_price or 0.0) * qty

                if ex.signal_type == "BUY":
                    s["buys"] += 1
                    running_buy_cost[key] += val
                    running_buy_qty[key] += qty
                elif ex.signal_type == "SELL":
                    s["sells"] += 1
                    s["cycles"] += 1
                    # Calculate this cycle's PnL
                    if running_buy_qty[key] > 0:
                        avg_cost = running_buy_cost[key] / running_buy_qty[key]
                        cycle_pnl = val - (qty * avg_cost)
                        cycle_pnls[key].append(round(cycle_pnl, 2))
                        # Reduce running buy position by sold qty
                        remaining_qty = running_buy_qty[key] - qty
                        if remaining_qty <= 0:
                            running_buy_cost[key] = 0.0
                            running_buy_qty[key] = 0.0
                        else:
                            running_buy_cost[key] = avg_cost * remaining_qty
                            running_buy_qty[key] = remaining_qty
                    else:
                        cycle_pnls[key].append(0.0)

            # Compute stats per mode
            for key in ["paper", "real"]:
                pnls = cycle_pnls[key]
                total_pnl = sum(pnls)
                stats[key]["realized_pnl"] = round(total_pnl, 2)

                if pnls:
                    wins = sum(1 for p in pnls if p > 0)
                    stats[key]["win_rate"] = round((wins / len(pnls)) * 100, 2)
                    stats[key]["wins"] = wins
                    stats[key]["max_pnl"] = round(max(pnls), 2)
                    stats[key]["min_pnl"] = round(min(pnls), 2)
                    # Recent 10 win rate
                    recent = pnls[-10:]
                    recent_wins = sum(1 for p in recent if p > 0)
                    stats[key]["recent_10_win_rate"] = round((recent_wins / len(recent)) * 100, 2)
                    stats[key]["recent_10_wins"] = recent_wins
                    stats[key]["recent_10_total"] = len(recent)
                    # PnL percentage (based on total buy cost used for sold cycles)
                    total_sold_cost = sum(
                        (ex.executed_price or 0) * (ex.filled_quantity or 0)
                        for ex in executions
                        if ex.signal_type == "BUY"
                        and ((ex.is_paper if ex.is_paper is not None else True) == (key == "paper"))
                    )
                    if total_sold_cost > 0:
                        stats[key]["realized_pnl_pct"] = round((total_pnl / total_sold_cost) * 100, 2)
                    else:
                        stats[key]["realized_pnl_pct"] = 0.0
                else:
                    stats[key]["realized_pnl_pct"] = 0.0
                    stats[key]["win_rate"] = 0.0
                    stats[key]["wins"] = 0
                    stats[key]["max_pnl"] = 0.0
                    stats[key]["min_pnl"] = 0.0
                    stats[key]["recent_10_win_rate"] = 0.0
                    stats[key]["recent_10_wins"] = 0
                    stats[key]["recent_10_total"] = 0

            return stats
        except Exception as e:
            logger.error(f"Trade stats error: {e}")
            error_logger.log_error(
                error_type=ErrorType.DB_ERROR,
                message=f"Trade stats error: {e}",
                session_id=self.session_id,
                exception=e,
                source_function="get_trade_stats"
            )
            return {"paper": {}, "real": {}}
        finally:
            db.close()

    @property
    def holdings(self) -> Dict[str, int]:
        return self._holdings

    def buy(self, symbol: str, quantity: int, price: float = 0, order_type: str = "market", metadata: Dict[str, Any] = None, on_filled: Callable = None) -> Dict[str, Any]:
        # Exclusive mode: check if another session holds the trading lock
        if self._exclusive_gate and not self._exclusive_gate():
            self.log(f"BUY BLOCKED: Exclusive lock held by another session")
            return {"status": "failed", "reason": "exclusive_locked"}
        return self._execute_order(symbol, OrderSide.BUY, quantity, price, metadata, on_filled)

    def sell(self, symbol: str, quantity: int, price: float = 0, order_type: str = "market", metadata: Dict[str, Any] = None, on_filled: Callable = None) -> Dict[str, Any]:
        return self._execute_order(symbol, OrderSide.SELL, quantity, price, metadata, on_filled)

    def short(self, symbol: str, quantity: float, price: float = 0, metadata: Dict[str, Any] = None, on_filled: Callable = None) -> Dict[str, Any]:
        """Open a short position (futures only). Uses place_short_order on FuturesInterface."""
        if not isinstance(self.adapter, FuturesInterface):
            self.log("SHORT FAILED: Adapter does not support futures")
            return {"status": "failed", "reason": "not_futures_adapter"}
        # Short orders use SELL side internally
        return self._execute_order(symbol, OrderSide.SELL, quantity, price,
                                   {**(metadata or {}), "position_side": "SHORT"}, on_filled)

    def close_position(self, symbol: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """Close entire position (futures only). Delegates to adapter.close_position()."""
        if not isinstance(self.adapter, FuturesInterface):
            self.log("CLOSE_POSITION FAILED: Adapter does not support futures")
            return {"status": "failed", "reason": "not_futures_adapter"}
        # Queue a close-position signal (handled in process_queue)
        current_price = self.get_current_price(symbol)
        qty = abs(self._holdings.get(symbol, 0))
        if qty == 0:
            return {"status": "success", "message": "No position to close"}
        side = OrderSide.SELL if self._holdings.get(symbol, 0) > 0 else OrderSide.BUY
        return self._execute_order(symbol, side, qty, 0,
                                   {**(metadata or {}), "close_position": True}, None)

    def _execute_order(self, symbol: str, side: OrderSide, quantity: float, price: float, metadata: Dict[str, Any] = None, on_filled: Callable = None) -> Dict[str, Any]:
        """
        Core Execution Pipeline:
        1. Validate (StockOrder)
        2. DB Record (PENDING)
        3. Send to Adapter
        4. DB Update (SUBMITTED/FAILED)
        5. Invoke on_filled callback after FILLED (in process_queue)
        """
        db: Session = SessionLocal()
        try:
            current_price = self.get_current_price(symbol)
            exec_price = price if price > 0 else current_price

            # 1. Create & Validate Order Object
            order = StockOrder(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=exec_price if price > 0 else None,
                order_type=OrderType.LIMIT if price > 0 else OrderType.MARKET
            )
            order.validate()

            # 2. Pre-Execution DB Record
            db_exec = LiveTradeExecution(
                session_id=self.session_id,
                symbol=symbol,
                signal_type=side.value,
                signal_timestamp=self.get_time(),
                theoretical_price=current_price,
                requested_quantity=quantity,
                status=ExecutionStatus.PENDING,
                is_paper=self._is_paper,
                trade_metadata=metadata,
                config_snapshot=self._config_snapshot  # 전략 파라미터 스냅샷
            )
            db.add(db_exec)
            db.commit() # Save ID
            db.refresh(db_exec)

            self.log(f"SIGNAL: {side.value} {quantity} {symbol} @ {exec_price}")

            # 3. Store callback for invocation after fill (in process_queue)
            if on_filled:
                self._order_callbacks[db_exec.id] = on_filled

            self.log(f"Queued Order: {side.value} {symbol}")

            # Return a "Receipt" (Trade Dict) immediately
            trade_receipt = {
                "type": side.value.lower(),
                "symbol": symbol,
                "price": exec_price,
                "quantity": quantity,
                "time": self.get_time().isoformat(),
                "order_id": db_exec.id, # Internal DB ID
                "status": "queued",
                "metadata": metadata or {}
            }
            self.trades.append(trade_receipt)
            return trade_receipt
            
        except Exception as e:
            self.log(f"ORDER ERROR: {e}")
            error_logger.log_order_error(
                message=f"Order execution error: {e}",
                session_id=self.session_id,
                symbol=symbol,
                exception=e,
                context={"side": side.value, "quantity": quantity, "price": price}
            )
            return {"status": "failed", "reason": str(e)}
        finally:
            db.close()

    def log(self, message: str):
        print(f"[LIVE] {message}")
        self.logs.append(f"[{self.get_time().strftime('%H:%M:%S')}] {message}")

    def reset_cycle_capital(self):
        """
        Reset cash to initial_capital for Fixed betting mode.
        Called by DipMartingale after closing a cycle.
        """
        self.cash = self.initial_capital
        self.log(f"Cycle Capital Reset: Cash → {self.initial_capital:,.0f}")

    def _restore_trades_from_db(self):
        """Restore in-memory trades list from DB on session recovery."""
        db = SessionLocal()
        try:
            executions = db.query(LiveTradeExecution).filter(
                LiveTradeExecution.session_id == self.session_id,
                LiveTradeExecution.status == ExecutionStatus.FILLED
            ).order_by(LiveTradeExecution.signal_timestamp).all()

            for ex in executions:
                trade = {
                    "type": ex.signal_type.lower(),
                    "symbol": ex.symbol,
                    "price": ex.executed_price or ex.theoretical_price,
                    "quantity": ex.filled_quantity or ex.requested_quantity,
                    "time": ex.order_filled_at.isoformat() if ex.order_filled_at else ex.signal_timestamp.isoformat(),
                    "order_id": ex.id,
                    "status": "filled",
                    "is_paper": ex.is_paper if ex.is_paper is not None else True,
                    "metadata": ex.trade_metadata or {}
                }
                self.trades.append(trade)

            if executions:
                logger.info(f"Context {self.session_id}: Restored {len(executions)} trades from DB")
        except Exception as e:
            logger.error(f"Trade restore error: {e}")
            error_logger.log_error(
                error_type=ErrorType.DB_ERROR,
                message=f"Trade restore error: {e}",
                session_id=self.session_id,
                exception=e,
                source_function="_restore_trades_from_db"
            )
        finally:
            db.close()

    def _sync_balance(self):
        pass

    async def async_sync_balance(self):
        """Called by Engine to update state"""
        try:
            bal = await self.adapter.get_balance()
            if bal:
                # SAFEGUARD: If adapter returns 0 cash (mock/error) but we have initial_capital,
                # preserve initial_capital for PnL consistency in simulation/test.
                # Support multi-currency: USDT (Binance) or KRW (Korean exchanges)
                cash_dict = bal.get('cash', {})
                fetched_cash = cash_dict.get('USDT') or cash_dict.get('KRW', 0)
                
                if fetched_cash == 0 and self.initial_capital > 0 and self.cash == self.initial_capital:
                    logger.warning("Balance Sync returned 0 cash. Preserving initial_capital for simulation.")
                    # Keep self.cash as is
                else:
                    self.cash = fetched_cash
                
                simple_holdings = {}
                for sym, data in bal['holdings'].items():
                    simple_holdings[sym] = data['quantity']
                self._holdings = simple_holdings
                
                # Update price map for all holdings to ensure get_total_equity is accurate
                for sym, data in bal['holdings'].items():
                    if 'current_price' in data and data['current_price'] > 0:
                        self.price_map[sym] = data['current_price']
                        
        except Exception as e:
            logger.error(f"Balance Sync Error: {e}")
            error_logger.log_error(
                error_type=ErrorType.BALANCE_SYNC_ERROR,
                message=f"Balance Sync Error: {e}",
                session_id=self.session_id,
                exception=e,
                source_function="async_sync_balance"
            )

    async def process_queue(self):
        """
        Called by Engine to process PENDING orders in DB/Queue.
        This is where 'Async Adapter' is actually called.

        CRITICAL: Each order is processed in its own isolated DB transaction.
        This prevents one order's failure from affecting others.
        """
        # First, get list of pending execution IDs (lightweight query)
        db_query: Session = SessionLocal()
        try:
            pending_ids = [
                p.id for p in db_query.query(LiveTradeExecution.id).filter(
                    LiveTradeExecution.session_id == self.session_id,
                    LiveTradeExecution.status == ExecutionStatus.PENDING
                ).all()
            ]
        finally:
            db_query.close()

        # Process each order in its own isolated transaction
        for execution_id in pending_ids:
            db: Session = SessionLocal()
            try:
                # Re-fetch the execution in this session's transaction
                p = db.query(LiveTradeExecution).filter(
                    LiveTradeExecution.id == execution_id,
                    LiveTradeExecution.status == ExecutionStatus.PENDING  # Double-check still pending
                ).first()

                if not p:
                    # Already processed by another thread/process or status changed
                    continue
                # Execute using OrderExecutionService
                try:
                    from ..services.order_execution_service import OrderExecutionService, OrderExecutionError

                    service = OrderExecutionService(self.adapter)
                    try:
                        res = await service.execute_order(
                            symbol=p.symbol,
                            side=p.signal_type.lower(),
                            quantity=p.requested_quantity,
                            price=0,  # Market order
                            is_paper=self.is_paper,
                            theoretical_price=p.theoretical_price
                        )
                        if self.is_paper:
                            self.log(f"PAPER SIGNAL: {p.signal_type} {p.symbol} @ {p.theoretical_price}")
                    except OrderExecutionError as e:
                        res = {"status": "failed", "message": e.message}

                    # Retry with reduced qty if margin insufficient
                    if res and res.get("status") == "failed":
                        error_msg = res.get("message", "")
                        match = re.search(r'(\d+)주 매수가능', error_msg)
                        if match and p.signal_type == "BUY":
                            available_qty = int(match.group(1))
                            if 0 < available_qty < p.requested_quantity:
                                self.log(f"RETRY: Reducing qty {p.requested_quantity} → {available_qty} (margin limit)")
                                p.requested_quantity = available_qty
                                try:
                                    res = await service.execute_order(
                                        symbol=p.symbol,
                                        side=p.signal_type.lower(),
                                        quantity=available_qty,
                                        price=0,
                                        is_paper=self.is_paper,
                                        theoretical_price=p.theoretical_price
                                    )
                                except OrderExecutionError as e2:
                                    res = {"status": "failed", "message": e2.message}

                    if res and res.get("status") == "success":
                        # 1. Update DB Record
                        p.status = ExecutionStatus.FILLED
                        p.order_submitted_at = self.get_time()
                        p.order_filled_at = self.get_time()
                        # Kiwoom 주문번호 저장 (WebSocket 체결 이벤트 매칭용)
                        p.exchange_order_no = res.get("order_id")
                        # 시장가 주문은 Kiwoom이 체결가를 즉시 반환하지 않으므로 theoretical_price를 추정치로 사용
                        # WebSocket 체결 콜백에서 실제 체결가로 업데이트됨
                        p.executed_price = res.get("price") or p.theoretical_price
                        p.filled_quantity = res.get("quantity", p.requested_quantity)

                        # 2. Calculate realized_pnl for SELL orders
                        if p.signal_type == "SELL":
                            try:
                                # Query all FILLED BUY executions for this session+symbol
                                buys = db.query(LiveTradeExecution).filter(
                                    LiveTradeExecution.session_id == self.session_id,
                                    LiveTradeExecution.symbol == p.symbol,
                                    LiveTradeExecution.signal_type == "BUY",
                                    LiveTradeExecution.status == ExecutionStatus.FILLED,
                                ).all()
                                total_buy_cost = sum((b.executed_price or 0) * (b.filled_quantity or 0) for b in buys)
                                total_buy_qty = sum(b.filled_quantity or 0 for b in buys)
                                if total_buy_qty > 0:
                                    avg_buy_price = total_buy_cost / total_buy_qty
                                    p.realized_pnl = round((p.executed_price - avg_buy_price) * p.filled_quantity, 2)
                                    p.slippage = round(p.executed_price - p.theoretical_price, 2)
                                    p.slippage_percent = round((p.slippage / p.theoretical_price) * 100, 4) if p.theoretical_price else 0
                                    self.log(f"PnL: {p.realized_pnl:+,.0f} (avg_cost={avg_buy_price:,.0f}, sell={p.executed_price:,.0f}, qty={p.filled_quantity})")
                            except Exception as pnl_err:
                                logger.error(f"PnL calc error: {pnl_err}")

                        # 3. Update Local Context State (In-Memory for Strategy)
                        # This ensures the bot's internal view is based on its OWN actions
                        cost = p.executed_price * p.filled_quantity
                        if p.signal_type == "BUY":
                            self.cash -= cost
                            self._holdings[p.symbol] = self._holdings.get(p.symbol, 0) + p.filled_quantity
                        else:
                            self.cash += cost
                            self._holdings[p.symbol] = self._holdings.get(p.symbol, 0) - p.filled_quantity

                        self.log(f"FILLED: {p.signal_type} {p.filled_quantity} {p.symbol} @ {p.executed_price}")

                        # 4. Invoke on_filled callback (for strategy position update)
                        if p.id in self._order_callbacks:
                            try:
                                callback = self._order_callbacks.pop(p.id)
                                callback(
                                    order_id=p.id,
                                    filled_qty=p.filled_quantity,
                                    filled_price=p.executed_price,
                                    metadata=p.trade_metadata or {}
                                )
                            except Exception as cb_err:
                                # CRITICAL: Callback failure means strategy position tracking is inconsistent
                                logger.error(f"CRITICAL: Order callback error - position state may be inconsistent: {cb_err}")
                                logger.error(traceback.format_exc())

                                # Log critical error for visibility
                                error_logger.log_critical(
                                    error_type=ErrorType.STRATEGY_ERROR,
                                    message=f"Order callback failed - position state may be inconsistent",
                                    session_id=self.session_id,
                                    symbol=p.symbol,
                                    exception=cb_err,
                                    context={
                                        "order_id": p.id,
                                        "signal_type": p.signal_type,
                                        "filled_qty": p.filled_quantity,
                                        "filled_price": p.executed_price
                                    }
                                )

                                # Update session to ERROR state so user is aware
                                try:
                                    sess = db.query(LiveBotSession).filter_by(id=self.session_id).first()
                                    if sess:
                                        sess.status = SessionStatus.ERROR
                                        sess.error_log = f"Callback error: {cb_err} - Position state may be inconsistent. Manual verification required."
                                        db.commit()
                                        logger.warning(f"Session {self.session_id} marked as ERROR due to callback failure")
                                except Exception as db_err:
                                    logger.error(f"Failed to update session status: {db_err}")

                        # 5. Send Telegram notification (fire and forget)
                        if self._user_id:
                            try:
                                import asyncio
                                from .telegram_service import send_telegram_notification
                                # Calculate return percentage for SELL orders
                                return_pct = None
                                if p.signal_type == "SELL" and p.realized_pnl and p.executed_price and p.filled_quantity:
                                    cost = (p.executed_price * p.filled_quantity) - p.realized_pnl
                                    if cost > 0:
                                        return_pct = (p.realized_pnl / cost) * 100

                                asyncio.create_task(send_telegram_notification(
                                    db=db,
                                    user_id=self._user_id,
                                    notification_type="trade",
                                    account_id=self._account_id,
                                    symbol=p.symbol,
                                    side=p.signal_type,
                                    quantity=p.filled_quantity,
                                    price=p.executed_price,
                                    strategy_name=self._strategy_name or "Unknown",
                                    is_paper=self._is_paper,
                                    pnl=p.realized_pnl if p.signal_type == "SELL" else None,
                                    return_pct=return_pct
                                ))
                            except Exception as tg_err:
                                logger.debug(f"Telegram notification skipped: {tg_err}")

                    elif res and res.get("status") == "submitted":
                        # ===== 실거래 주문 접수 완료 → 체결 확인 필요 =====
                        # return_code=0 은 "주문 접수"일 뿐, 체결이 아님.
                        # get_balance()로 실제 보유수량 변동을 확인해야 함.
                        p.status = ExecutionStatus.SUBMITTED
                        p.exchange_order_no = res.get("order_id")
                        p.order_submitted_at = self.get_time()
                        db.commit()
                        self.log(f"SUBMITTED: {p.signal_type} {p.requested_quantity} {p.symbol} (order_no={p.exchange_order_no})")

                        # 체결 대기 (시장가 주문은 보통 1초 이내 체결)
                        await asyncio.sleep(1.5)

                        # ===== ka10076 체결 내역 API로 직접 확인 (3회 폴링) =====
                        fill_verified = False
                        try:
                            for attempt in range(3):
                                executions = await self.adapter.get_order_executions(
                                    order_no=p.exchange_order_no, symbol=p.symbol
                                )
                                if executions:
                                    ex = executions[0]
                                    if ex["filled_qty"] > 0:
                                        p.status = ExecutionStatus.FILLED
                                        p.order_filled_at = self.get_time()
                                        p.executed_price = ex["filled_price"] or p.theoretical_price
                                        p.filled_quantity = ex["filled_qty"]
                                        p.fees = ex.get("commission", 0) + ex.get("tax", 0)
                                        fill_verified = True
                                        self.log(
                                            f"FILLED (ka10076): {p.signal_type} {p.filled_quantity} {p.symbol} "
                                            f"@ {p.executed_price:,.0f} "
                                            f"(commission={ex.get('commission', 0):,.0f}, tax={ex.get('tax', 0):,.0f})"
                                        )
                                        break

                                    ord_status = ex.get("status", "")
                                    if "취소" in ord_status or "거부" in ord_status:
                                        p.status = ExecutionStatus.CANCELLED
                                        p.error_reason = f"Order cancelled/rejected: {ord_status}"
                                        fill_verified = True
                                        self.log(f"CANCELLED (ka10076): {p.symbol} - {ord_status}")
                                        break

                                if attempt < 2:
                                    self.log(f"Fill not confirmed yet (attempt {attempt + 1}/3), retrying...")
                                    await asyncio.sleep(1.0)
                        except Exception as api_err:
                            logger.warning(f"ka10076 API error, falling back to balance check: {api_err}")

                        # ===== Fallback: get_balance() 잔고 비교 (ka10076 미확인 시) =====
                        if not fill_verified:
                            self.log(f"ka10076 unconfirmed, falling back to balance verification")
                            try:
                                balance = await self.adapter.get_balance()
                                actual_holdings = balance.get("holdings", {})
                                actual_qty = actual_holdings.get(p.symbol, {}).get("quantity", 0)
                                prev_qty = self._holdings.get(p.symbol, 0)

                                if p.signal_type == "BUY":
                                    filled_qty = actual_qty - prev_qty
                                    if filled_qty > 0:
                                        actual_price = actual_holdings.get(p.symbol, {}).get("avg_price", 0)
                                        p.status = ExecutionStatus.FILLED
                                        p.order_filled_at = self.get_time()
                                        p.executed_price = actual_price or p.theoretical_price
                                        p.filled_quantity = filled_qty
                                        self.log(f"FILLED (balance-fallback): BUY {filled_qty} {p.symbol} @ {p.executed_price}")
                                    else:
                                        p.status = ExecutionStatus.FAILED
                                        p.error_reason = f"Fill unconfirmed: ka10076 empty, balance unchanged (prev={prev_qty}, actual={actual_qty})"
                                        self.log(f"FILL VERIFY FAILED: BUY {p.symbol} - no quantity change (prev={prev_qty}, actual={actual_qty})")
                                else:  # SELL
                                    qty_decreased = prev_qty - actual_qty
                                    if qty_decreased > 0:
                                        p.status = ExecutionStatus.FILLED
                                        p.order_filled_at = self.get_time()
                                        p.executed_price = p.theoretical_price
                                        p.filled_quantity = qty_decreased
                                        self.log(f"FILLED (balance-fallback): SELL {qty_decreased} {p.symbol} @ {p.executed_price}")
                                    else:
                                        p.status = ExecutionStatus.FAILED
                                        p.error_reason = f"Fill unconfirmed: ka10076 empty, balance unchanged (prev={prev_qty}, actual={actual_qty})"
                                        self.log(f"FILL VERIFY FAILED: SELL {p.symbol} - no quantity change (prev={prev_qty}, actual={actual_qty})")
                            except Exception as verify_err:
                                logger.error(f"Balance fallback error: {verify_err}")
                                p.status = ExecutionStatus.FAILED
                                p.error_reason = f"Verification failed: ka10076 + balance both failed: {verify_err}"
                                self.log(f"FILL VERIFY ERROR: {p.symbol} - {verify_err}")

                        # ===== FILLED 후처리: _holdings 동기화 + PnL 계산 =====
                        if p.status == ExecutionStatus.FILLED:
                            # get_balance()로 정확한 보유수량/현금 동기화
                            try:
                                sync_balance = await self.adapter.get_balance()
                                sync_holdings = sync_balance.get("holdings", {})
                                self._holdings[p.symbol] = sync_holdings.get(p.symbol, {}).get("quantity", 0)
                                self.cash = sync_balance.get("cash", {}).get("KRW", self.cash)
                            except Exception as sync_err:
                                logger.warning(f"Post-fill balance sync failed: {sync_err}")
                                # Manual fallback
                                if p.signal_type == "BUY":
                                    self._holdings[p.symbol] = self._holdings.get(p.symbol, 0) + p.filled_quantity
                                    self.cash -= p.executed_price * p.filled_quantity
                                else:
                                    self._holdings[p.symbol] = max(0, self._holdings.get(p.symbol, 0) - p.filled_quantity)
                                    self.cash += p.executed_price * p.filled_quantity

                            # SELL PnL 계산
                            if p.signal_type == "SELL":
                                try:
                                    buys = db.query(LiveTradeExecution).filter(
                                        LiveTradeExecution.session_id == self.session_id,
                                        LiveTradeExecution.symbol == p.symbol,
                                        LiveTradeExecution.signal_type == "BUY",
                                        LiveTradeExecution.status == ExecutionStatus.FILLED,
                                    ).all()
                                    total_buy_cost = sum((b.executed_price or 0) * (b.filled_quantity or 0) for b in buys)
                                    total_buy_qty = sum(b.filled_quantity or 0 for b in buys)
                                    if total_buy_qty > 0:
                                        avg_buy_price = total_buy_cost / total_buy_qty
                                        p.realized_pnl = round((p.executed_price - avg_buy_price) * p.filled_quantity, 2)
                                        self.log(f"PnL: {p.realized_pnl:+,.0f} (avg_cost={avg_buy_price:,.0f}, sell={p.executed_price:,.0f})")
                                except Exception as pnl_err:
                                    logger.error(f"PnL calc error: {pnl_err}")

                        # Invoke callback based on final status
                        if p.status == ExecutionStatus.FILLED and p.id in self._order_callbacks:
                            try:
                                callback = self._order_callbacks.pop(p.id)
                                callback(
                                    order_id=p.id,
                                    filled_qty=p.filled_quantity,
                                    filled_price=p.executed_price,
                                    metadata=p.trade_metadata or {}
                                )
                            except Exception as cb_err:
                                logger.error(f"Order callback error: {cb_err}")
                        elif p.status in (ExecutionStatus.FAILED, ExecutionStatus.CANCELLED) and p.id in self._order_callbacks:
                            try:
                                callback = self._order_callbacks.pop(p.id)
                                callback(
                                    order_id=p.id,
                                    filled_qty=0,
                                    filled_price=0,
                                    metadata=p.trade_metadata or {}
                                )
                            except Exception as cb_err:
                                logger.error(f"Order failure callback error: {cb_err}")

                        # Telegram notification for FILLED
                        if p.status == ExecutionStatus.FILLED and self._user_id:
                            try:
                                import asyncio as _asyncio
                                from .telegram_service import send_telegram_notification
                                return_pct = None
                                if p.signal_type == "SELL" and p.realized_pnl and p.executed_price and p.filled_quantity:
                                    cost = (p.executed_price * p.filled_quantity) - p.realized_pnl
                                    if cost > 0:
                                        return_pct = (p.realized_pnl / cost) * 100
                                _asyncio.create_task(send_telegram_notification(
                                    db=db,
                                    user_id=self._user_id,
                                    notification_type="trade",
                                    account_id=self._account_id,
                                    symbol=p.symbol,
                                    side=p.signal_type,
                                    quantity=p.filled_quantity,
                                    price=p.executed_price,
                                    strategy_name=self._strategy_name or "Unknown",
                                    is_paper=self._is_paper,
                                    pnl=p.realized_pnl if p.signal_type == "SELL" else None,
                                    return_pct=return_pct
                                ))
                            except Exception as tg_err:
                                logger.debug(f"Telegram notification skipped: {tg_err}")

                    elif res:
                        p.status = ExecutionStatus.FAILED
                        p.error_reason = res.get("message", "Unknown Error")
                        self.log(f"ORDER FAILED: {p.error_reason}")
                        error_logger.log_order_error(
                            message=f"Order failed: {p.error_reason}",
                            session_id=self.session_id,
                            symbol=p.symbol,
                            context={"signal_type": p.signal_type, "quantity": p.requested_quantity}
                        )
                        # Invoke callback with filled_qty=0 to signal failure (allows strategy to clear pending flags)
                        if p.id in self._order_callbacks:
                            try:
                                callback = self._order_callbacks.pop(p.id)
                                callback(
                                    order_id=p.id,
                                    filled_qty=0,  # Signal failure
                                    filled_price=0,
                                    metadata=p.trade_metadata or {}
                                )
                            except Exception as cb_err:
                                logger.error(f"Order failure callback error: {cb_err}")

                    db.commit()
                except Exception as e:
                    logger.error(f"Queue Process Error for execution {execution_id}: {e}")
                    error_logger.log_order_error(
                        message=f"Queue Process Error: {e}",
                        session_id=self.session_id,
                        symbol=p.symbol if p else None,
                        exception=e,
                        context={"execution_id": execution_id}
                    )
                    db.rollback()
            except Exception as e:
                # DB-level error for this specific order
                logger.error(f"Queue DB Error for execution {execution_id}: {e}")
                error_logger.log_error(
                    error_type=ErrorType.DB_ERROR,
                    message=f"Queue DB Error: {e}",
                    session_id=self.session_id,
                    exception=e,
                    source_function="process_queue",
                    context={"execution_id": execution_id}
                )
            finally:
                # CRITICAL: Each order gets its own session, must close it
                db.close()
