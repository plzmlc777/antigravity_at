"""
OrderExecutionService - Unified Order Execution Logic

Consolidates order execution from:
- Manual API (endpoints.py)
- Live Context (live_context.py)

Single source of truth for order execution, logging, and error handling.
"""

from typing import Dict, Any, Optional
from datetime import datetime
import logging
from sqlalchemy.orm import Session

from ..core.exchange_interface import ExchangeInterface
from ..core.futures_interface import FuturesInterface
from ..core.constants import Signal, Side
from ..models.live_trading import LiveTradeExecution, ExecutionStatus
from ..services.error_logger import error_logger
from ..models.live_trading import ErrorType

logger = logging.getLogger(__name__)


class OrderExecutionError(Exception):
    """Custom exception for order execution failures"""
    def __init__(self, message: str, details: Dict[str, Any] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class OrderExecutionService:
    """
    Unified service for executing stock orders.

    Usage:
        # Manual API (no DB logging)
        service = OrderExecutionService(adapter)
        result = await service.execute_order("005930", "buy", 10, price=75000)

        # Live Context (with DB logging)
        service = OrderExecutionService(adapter, db, session_id="abc-123")
        result = await service.execute_order("005930", "buy", 10, log_to_db=True)
    """

    def __init__(
        self,
        adapter: ExchangeInterface,
        db: Session = None,
        session_id: str = None
    ):
        self.adapter = adapter
        self.db = db
        self.session_id = session_id

    async def execute_order(
        self,
        symbol: str,
        side: str,  # "buy" or "sell"
        quantity: float,  # Float to support fractional crypto (e.g. 0.131 BTC)
        price: float = 0,
        log_to_db: bool = False,
        is_paper: bool = False,
        theoretical_price: float = None,
        metadata: Dict[str, Any] = None,
        config_snapshot: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Execute a stock order with unified logic.

        Args:
            symbol: Stock symbol (e.g., "005930")
            side: "buy" or "sell"
            quantity: Number of shares
            price: Order price (0 for market order)
            log_to_db: Whether to log execution to DB (for Live)
            is_paper: Paper trading mode (skip real API call)
            theoretical_price: Expected price at signal time (for slippage calc)
            metadata: Additional trade metadata
            config_snapshot: Strategy config snapshot (for Live)

        Returns:
            Dict with order result including status, order_id, price, quantity

        Raises:
            OrderExecutionError: If order fails
        """
        execution_id = None

        try:
            # 1. Pre-execution DB logging (if enabled)
            if log_to_db and self.db and self.session_id:
                execution_id = self._create_pending_execution(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    theoretical_price=theoretical_price or price,
                    is_paper=is_paper,
                    metadata=metadata,
                    config_snapshot=config_snapshot
                )

            # 2. Execute order
            if is_paper:
                # Paper trading - simulate success
                result = {
                    "status": "success",
                    "order_id": f"PAPER-{datetime.now().strftime('%H%M%S')}",
                    "price": theoretical_price or price,
                    "quantity": quantity,
                    "message": "Paper Execution (Simulated)"
                }
                logger.info(f"[PAPER] {side.upper()} {quantity} {symbol} @ {result['price']}")
            else:
                # Real trading - call adapter
                result = await self._call_adapter(symbol, side, price, quantity, metadata=metadata)

            # 3. Post-execution DB update (if enabled)
            if log_to_db and self.db and execution_id:
                self._update_execution_result(
                    execution_id=execution_id,
                    result=result,
                    theoretical_price=theoretical_price
                )

            # 4. Check result
            if result.get("status") == "failed":
                raise OrderExecutionError(
                    result.get("message", "Order failed"),
                    details=result
                )

            return result

        except OrderExecutionError:
            raise
        except Exception as e:
            logger.error(f"Order execution error: {e}")

            # Log error to DB if enabled
            if log_to_db and self.db and execution_id:
                self._mark_execution_failed(execution_id, str(e))

            error_logger.log_order_error(
                message=f"Order execution error: {e}",
                session_id=self.session_id,
                symbol=symbol,
                exception=e,
                context={"side": side, "quantity": quantity, "price": price}
            )

            raise OrderExecutionError(str(e))

    async def _call_adapter(
        self,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Call the exchange adapter to place order"""
        metadata = metadata or {}

        # Futures: close_position uses adapter.close_position() directly
        if metadata.get("close_position") and isinstance(self.adapter, FuturesInterface):
            return await self.adapter.close_position(symbol)

        # Futures: short order uses place_short_order()
        if metadata.get("position_side", "").lower() == Side.SHORT and isinstance(self.adapter, FuturesInterface):
            return await self.adapter.place_short_order(symbol, price, quantity)

        if side.lower() == "buy":
            return await self.adapter.place_buy_order(symbol, price, quantity)
        elif side.lower() == "sell":
            return await self.adapter.place_sell_order(symbol, price, quantity)
        else:
            raise OrderExecutionError(f"Invalid order side: {side}")

    def _create_pending_execution(
        self,
        symbol: str,
        side: str,
        quantity: float,
        theoretical_price: float,
        is_paper: bool,
        metadata: Dict[str, Any],
        config_snapshot: Dict[str, Any]
    ) -> int:
        """Create a PENDING execution record in DB"""
        execution = LiveTradeExecution(
            session_id=self.session_id,
            symbol=symbol,
            signal_type=side.upper(),
            signal_timestamp=datetime.now(),
            theoretical_price=theoretical_price,
            requested_quantity=quantity,
            status=ExecutionStatus.PENDING,
            is_paper=is_paper,
            trade_metadata=metadata,
            config_snapshot=config_snapshot
        )
        self.db.add(execution)
        self.db.commit()
        self.db.refresh(execution)
        return execution.id

    def _update_execution_result(
        self,
        execution_id: int,
        result: Dict[str, Any],
        theoretical_price: float = None
    ):
        """Update execution record with result"""
        execution = self.db.query(LiveTradeExecution).filter(
            LiveTradeExecution.id == execution_id
        ).first()

        if not execution:
            return

        if result.get("status") == "success":
            execution.status = ExecutionStatus.FILLED
            execution.order_submitted_at = datetime.now()
            execution.order_filled_at = datetime.now()
            execution.exchange_order_no = result.get("order_id")
            execution.executed_price = result.get("price") or theoretical_price
            execution.filled_quantity = result.get("quantity", execution.requested_quantity)

            # Calculate slippage if we have theoretical price
            if theoretical_price and execution.executed_price:
                execution.slippage = round(execution.executed_price - theoretical_price, 2)
                if theoretical_price > 0:
                    execution.slippage_percent = round(
                        (execution.slippage / theoretical_price) * 100, 4
                    )

            # Calculate realized PnL for SELL orders
            if execution.signal_type == Signal.SELL:
                self._calculate_realized_pnl(execution)
        else:
            execution.status = ExecutionStatus.FAILED
            execution.error_reason = result.get("message", "Unknown Error")

        self.db.commit()

    def _calculate_realized_pnl(self, sell_execution: LiveTradeExecution):
        """Calculate realized PnL for a sell order"""
        try:
            # Get all filled BUY orders for this session and symbol
            buys = self.db.query(LiveTradeExecution).filter(
                LiveTradeExecution.session_id == self.session_id,
                LiveTradeExecution.symbol == sell_execution.symbol,
                LiveTradeExecution.signal_type == Signal.BUY,
                LiveTradeExecution.status == ExecutionStatus.FILLED,
            ).all()

            total_buy_cost = sum(
                (b.executed_price or 0) * (b.filled_quantity or 0) for b in buys
            )
            total_buy_qty = sum(b.filled_quantity or 0 for b in buys)

            if total_buy_qty > 0:
                avg_buy_price = total_buy_cost / total_buy_qty
                sell_execution.realized_pnl = round(
                    (sell_execution.executed_price - avg_buy_price) * sell_execution.filled_quantity,
                    2
                )
                logger.info(
                    f"[PnL] {sell_execution.realized_pnl:+,.0f} "
                    f"(avg_cost={avg_buy_price:,.0f}, sell={sell_execution.executed_price:,.0f})"
                )
        except Exception as e:
            logger.error(f"PnL calculation error: {e}")

    def _mark_execution_failed(self, execution_id: int, error_reason: str):
        """Mark execution as failed"""
        try:
            execution = self.db.query(LiveTradeExecution).filter(
                LiveTradeExecution.id == execution_id
            ).first()
            if execution:
                execution.status = ExecutionStatus.FAILED
                execution.error_reason = error_reason
                self.db.commit()
        except Exception as e:
            logger.error(f"Failed to mark execution as failed: {e}")
