"""
Funding Rate Arbitrage Strategy
- Collects funding fees by taking positions opposite to the dominant funding rate direction.
- Positive funding rate → SHORT (shorts receive funding)
- Negative funding rate → LONG (longs receive funding)
- Exits when rate normalizes, max hold time exceeded, or max loss hit.
- Requires FuturesInterface adapter (REQUIRES_FUTURES = True).
"""

from typing import Dict, Any, Optional
from datetime import datetime
from .base import BaseStrategy, IContext
from .martingale_base import MartingaleBase

import logging
logger = logging.getLogger(__name__)


class FundingRateArbStrategy(MartingaleBase):
    """
    Funding Rate Arbitrage - single-direction futures position to collect funding fees.
    Inherits MartingaleBase for common parameter schema and position management infrastructure.
    Overrides on_data() with its own funding-rate-based entry/exit logic.
    """

    REQUIRES_FUTURES = True

    PARAMETER_SCHEMA = {
        "fields": [
            {"name": "entry_rate_threshold", "type": "number", "label": "Entry Rate (%)",
             "default": 0.03, "min": 0.001, "max": 1.0, "step": 0.001,
             "description": "Enter when |funding_rate| exceeds this % (e.g., 0.03 = 0.03%)",
             "group": "trigger", "show_in_table": True},
            {"name": "exit_rate_threshold", "type": "number", "label": "Exit Rate (%)",
             "default": 0.005, "min": 0.0, "max": 0.5, "step": 0.001,
             "description": "Exit when |funding_rate| drops below this %",
             "group": "trigger", "show_in_table": True},
            {"name": "position_size_pct", "type": "number", "label": "Position Size (%)",
             "default": 50.0, "min": 5, "max": 100, "step": 5,
             "description": "% of capital to use for position",
             "group": "common", "show_in_table": True},
        ] + BaseStrategy.COMMON_PARAMETER_FIELDS
    }

    def _initialize_trigger(self):
        """Initialize funding-rate-specific state."""
        self.entry_rate = self.config.get("entry_rate_threshold", 0.03) / 100  # Convert % to decimal
        self.exit_rate = self.config.get("exit_rate_threshold", 0.005) / 100
        self.position_size_pct = self.config.get("position_size_pct", 50.0) / 100

        # State
        self._position_side: Optional[str] = None  # "LONG" or "SHORT" or None
        self._entry_price: float = 0
        self._entry_time: Optional[datetime] = None
        self._position_qty: float = 0

    def on_data(self, data: Dict[str, Any]):
        symbol = data.get("symbol", self.symbol)
        current_price = data.get("close", 0)
        if current_price <= 0:
            return

        futures_data = self.context.get_futures_data(symbol)
        funding_rate = futures_data.get("funding_rate", 0)

        # If we have a position, check exit conditions
        if self._position_side:
            self._check_exit(symbol, current_price, funding_rate, futures_data)
        else:
            self._check_entry(symbol, current_price, funding_rate)

    def _check_entry(self, symbol: str, price: float, funding_rate: float):
        """Check if funding rate is extreme enough to enter."""
        if abs(funding_rate) < self.entry_rate:
            return

        # Calculate position size
        initial_capital = getattr(self.context, 'initial_capital', 10000)
        notional = initial_capital * self.position_size_pct
        qty = notional / price if price > 0 else 0

        if qty <= 0:
            return

        if funding_rate > 0:
            # Positive rate: shorts receive funding → go SHORT
            self.context.log(f"[FundingArb] SHORT signal: rate={funding_rate*100:.4f}% > threshold")
            result = self.context.short(symbol, qty, metadata={"reason": "funding_arb", "rate": funding_rate})
            if result.get("status") != "failed":
                self._position_side = "SHORT"
                self._entry_price = price
                self._entry_time = self.context.get_time()
                self._position_qty = qty
        else:
            # Negative rate: longs receive funding → go LONG
            self.context.log(f"[FundingArb] LONG signal: rate={funding_rate*100:.4f}% < -threshold")
            result = self.context.buy(symbol, int(qty) if qty >= 1 else qty,
                                      metadata={"reason": "funding_arb", "rate": funding_rate})
            if result.get("status") != "failed":
                self._position_side = "LONG"
                self._entry_price = price
                self._entry_time = self.context.get_time()
                self._position_qty = qty

    def _check_exit(self, symbol: str, price: float, funding_rate: float, futures_data: Dict):
        """Check exit conditions for existing position."""
        should_exit = False
        reason = ""

        # 1. Rate normalized (below exit threshold)
        if abs(funding_rate) < self.exit_rate:
            should_exit = True
            reason = f"rate_normalized ({funding_rate*100:.4f}%)"

        # 2. Rate reversed direction
        if not should_exit:
            if self._position_side == "SHORT" and funding_rate < -self.entry_rate:
                should_exit = True
                reason = f"rate_reversed ({funding_rate*100:.4f}%)"
            elif self._position_side == "LONG" and funding_rate > self.entry_rate:
                should_exit = True
                reason = f"rate_reversed ({funding_rate*100:.4f}%)"

        # 3. Max hold time
        if not should_exit and self.max_hold_hours > 0 and self._entry_time:
            elapsed = (self.context.get_time() - self._entry_time).total_seconds() / 3600
            if elapsed >= self.max_hold_hours:
                should_exit = True
                reason = f"max_hold ({elapsed:.1f}h)"

        # 4. Max loss
        if not should_exit and self._entry_price > 0:
            if self._position_side == "LONG":
                pnl_pct = (price - self._entry_price) / self._entry_price
            else:
                pnl_pct = (self._entry_price - price) / self._entry_price

            if pnl_pct <= -self.max_loss_pct:
                should_exit = True
                reason = f"max_loss ({pnl_pct*100:.2f}%)"

        if should_exit:
            self.context.log(f"[FundingArb] EXIT {self._position_side}: {reason}")
            try:
                self.context.close_position(symbol, metadata={"reason": reason})
            except NotImplementedError:
                # Fallback for backtest: sell/buy to close
                if self._position_side == "LONG":
                    self.context.sell(symbol, int(self._position_qty), metadata={"reason": reason})
                # Short close handled by FuturesBacktestContext
            self._position_side = None
            self._entry_price = 0
            self._entry_time = None
            self._position_qty = 0

    def _check_entry_trigger(self, data: Dict[str, Any]) -> bool:
        """Not used — funding_rate_arb uses its own on_data() flow."""
        return False

    def _check_additional_trigger(self, data: Dict[str, Any]) -> bool:
        """Not used — funding_rate_arb manages positions directly."""
        return False

    @property
    def _log_prefix(self) -> str:
        return "FundingArb"

    @property
    def _strategy_id(self) -> str:
        return "funding_rate_arb"

    def get_state(self) -> Dict[str, Any]:
        state = super().get_state()
        state["position_side"] = self._position_side or "NONE"
        state["arb_entry_price"] = self._entry_price
        state["arb_position_qty"] = self._position_qty
        state["arb_entry_time"] = self._entry_time.isoformat() if self._entry_time else None
        return state
