
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
from sqlalchemy.orm import Session
from ..db.session import SessionLocal
from ..models.live_trading import LiveTradeExecution, ExecutionStatus, ErrorType
from ..models.new_orders import StockOrder, OrderSide, OrderType
from ..adapters.kiwoom_real import KiwoomRealAdapter
from ..services.error_logger import error_logger

logger = logging.getLogger(__name__)

class LiveContext:
    """
    Context for Live Trading Strategies.
    Mimics BacktestContext interface but executes against Real Adapter & DB.
    """
    def __init__(self, session_id: str, adapter: KiwoomRealAdapter, initial_capital: float = 0.0, is_paper: bool = True):
        self.session_id = session_id
        self.adapter = adapter
        self.initial_capital = initial_capital
        self._is_paper = is_paper
        
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

            # Track average cost per mode for realized PnL
            total_bought_cost = {"paper": 0.0, "real": 0.0}
            total_bought_qty = {"paper": 0.0, "real": 0.0}
            total_sold_value = {"paper": 0.0, "real": 0.0}
            total_sold_qty = {"paper": 0.0, "real": 0.0}

            for ex in executions:
                is_paper = ex.is_paper if ex.is_paper is not None else True
                key = "paper" if is_paper else "real"
                s = stats[key]
                s["trades"] += 1
                qty = ex.filled_quantity or 0.0
                val = (ex.executed_price or 0.0) * qty

                if ex.signal_type == "BUY":
                    s["buys"] += 1
                    total_bought_cost[key] += val
                    total_bought_qty[key] += qty
                elif ex.signal_type == "SELL":
                    s["sells"] += 1
                    total_sold_value[key] += val
                    total_sold_qty[key] += qty
                    s["cycles"] += 1

            # Realized PnL: only for sold quantity using average buy cost
            for key in ["paper", "real"]:
                if total_bought_qty[key] > 0 and total_sold_qty[key] > 0:
                    avg_cost = total_bought_cost[key] / total_bought_qty[key]
                    realized = total_sold_value[key] - (total_sold_qty[key] * avg_cost)
                    sold_cost = total_sold_qty[key] * avg_cost
                    stats[key]["realized_pnl"] = round(realized, 2)
                    stats[key]["realized_pnl_pct"] = round((realized / sold_cost) * 100, 2) if sold_cost > 0 else 0.0
                else:
                    stats[key]["realized_pnl"] = 0.0
                    stats[key]["realized_pnl_pct"] = 0.0

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

    def buy(self, symbol: str, quantity: int, price: float = 0, order_type: str = "market", metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        return self._execute_order(symbol, OrderSide.BUY, quantity, price, metadata)

    def sell(self, symbol: str, quantity: int, price: float = 0, order_type: str = "market", metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        return self._execute_order(symbol, OrderSide.SELL, quantity, price, metadata)

    def _execute_order(self, symbol: str, side: OrderSide, quantity: float, price: float, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Core Execution Pipeline:
        1. Validate (StockOrder)
        2. DB Record (PENDING)
        3. Send to Adapter
        4. DB Update (SUBMITTED/FAILED)
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
            
            # ... (Async bridge logic placeholder) ...
            
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
                fetched_cash = bal['cash']['KRW']
                
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
        """
        db: Session = SessionLocal()
        try:
            # Find PENDING executions for this session
            pendings = db.query(LiveTradeExecution).filter(
                LiveTradeExecution.session_id == self.session_id,
                LiveTradeExecution.status == ExecutionStatus.PENDING
            ).all()
            
            for p in pendings:
                # Execute
                try:
                    res = None
                    if self.is_paper:
                        # Paper Trading: Skip Adapter Call
                        res = {
                            "status": "success",
                            "order_id": f"PAPER-{p.id[:8]}",
                            "price": p.theoretical_price,
                            "quantity": p.requested_quantity,
                            "message": "Paper Execution (Simulated)"
                        }
                        self.log(f"PAPER SIGNAL: {p.signal_type} {p.symbol} @ {p.theoretical_price}")
                    else:
                        # REAL Trading: Call Adapter with MARKET ORDER (price=0)
                        # 시장가 주문으로 즉시 체결 보장, theoretical_price는 슬리피지 분석용 보존
                        if p.signal_type == "BUY":
                            res = await self.adapter.place_buy_order(p.symbol, 0, p.requested_quantity)
                        elif p.signal_type == "SELL":
                            res = await self.adapter.place_sell_order(p.symbol, 0, p.requested_quantity)

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
                        
                    db.commit()
                except Exception as e:
                    logger.error(f"Queue Process Error: {e}")
                    error_logger.log_order_error(
                        message=f"Queue Process Error: {e}",
                        session_id=self.session_id,
                        symbol=p.symbol if p else None,
                        exception=e,
                        context={"execution_id": p.id if p else None}
                    )
                    db.rollback()
        except Exception as e:
            logger.error(f"Queue DB Error: {e}")
            error_logger.log_error(
                error_type=ErrorType.DB_ERROR,
                message=f"Queue DB Error: {e}",
                session_id=self.session_id,
                exception=e,
                source_function="process_queue"
            )
        finally:
            db.close()
