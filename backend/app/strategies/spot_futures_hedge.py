"""
Spot-Futures Hedge Strategy (Cash-and-Carry Arbitrage)
- Opens Spot LONG + Futures SHORT simultaneously when funding rate is high
- Collects funding fees while being market-neutral (hedged)
- Exits when funding rate normalizes or max hold time reached
- Requires BOTH a Spot and Futures account (REQUIRES_HEDGE = True)
"""

from typing import Dict, Any, Optional
from datetime import datetime
from .base import BaseStrategy, IContext
from .martingale_base import MartingaleBase

import logging
logger = logging.getLogger(__name__)


class SpotFuturesHedgeStrategy(MartingaleBase):
    """
    Cash-and-Carry Arbitrage: Spot Long + Futures Short.
    Earns funding fees while being delta-neutral.
    Inherits MartingaleBase for common parameter schema and position management infrastructure.
    Overrides on_data() with its own hedge-based entry/exit logic.
    """

    REQUIRES_FUTURES = True
    REQUIRES_HEDGE = True

    PARAMETER_SCHEMA = {
        "fields": [
            {"name": "entry_rate_threshold", "type": "number", "label": "Entry Rate (%)",
             "default": 0.05, "min": 0.001, "max": 1.0, "step": 0.001,
             "description": "Open hedge when funding rate exceeds this % (positive rate = shorts receive)",
             "group": "trigger", "show_in_table": True},
            {"name": "exit_rate_threshold", "type": "number", "label": "Exit Rate (%)",
             "default": 0.01, "min": 0.0, "max": 0.5, "step": 0.001,
             "description": "Close hedge when funding rate drops below this %",
             "group": "trigger", "show_in_table": True},
            {"name": "hedge_size_pct", "type": "number", "label": "Hedge Size (%)",
             "default": 50.0, "min": 10, "max": 100, "step": 5,
             "description": "% of capital for each leg of the hedge",
             "group": "common", "show_in_table": True},
            {"name": "spot_account_id", "type": "number", "label": "Spot Account ID",
             "default": 0, "min": 0, "max": 9999, "step": 1,
             "description": "Exchange account ID for spot leg",
             "group": "hedge", "show_in_table": False},
            {"name": "futures_account_id", "type": "number", "label": "Futures Account ID",
             "default": 0, "min": 0, "max": 9999, "step": 1,
             "description": "Exchange account ID for futures leg",
             "group": "hedge", "show_in_table": False},
        ] + BaseStrategy.COMMON_PARAMETER_FIELDS
    }

    def _initialize_trigger(self):
        """Initialize hedge-specific state."""
        self.entry_rate = self.config.get("entry_rate_threshold", 0.05) / 100
        self.exit_rate = self.config.get("exit_rate_threshold", 0.01) / 100
        self.hedge_size_pct = self.config.get("hedge_size_pct", 50.0) / 100

        # State
        self._is_hedged = False
        self._entry_time: Optional[datetime] = None
        self._entry_funding_rate: float = 0
        self._total_funding_collected: float = 0
        self._hedge_coordinator = None  # Set by LiveManager

    def set_hedge_coordinator(self, coordinator):
        """Called by LiveManager to inject the HedgeCoordinator."""
        self._hedge_coordinator = coordinator

    def on_data(self, data: Dict[str, Any]):
        symbol = data.get("symbol", self.symbol)
        current_price = data.get("close", 0)
        if current_price <= 0:
            return

        futures_data = self.context.get_futures_data(symbol)
        funding_rate = futures_data.get("funding_rate", 0)

        if self._is_hedged:
            self._check_exit(symbol, current_price, funding_rate)
        else:
            self._check_entry(symbol, current_price, funding_rate)

    def _check_entry(self, symbol: str, price: float, funding_rate: float):
        """Open hedge when funding rate is sufficiently positive (shorts receive)."""
        # Only enter on positive funding rate (shorts receive funding)
        if funding_rate < self.entry_rate:
            return

        if not self._hedge_coordinator:
            self.context.log("[Hedge] ERROR: No HedgeCoordinator configured")
            return

        initial_capital = getattr(self.context, 'initial_capital', 10000)
        notional = initial_capital * self.hedge_size_pct

        self.context.log(f"[Hedge] OPEN signal: rate={funding_rate*100:.4f}%, "
                        f"notional={notional:.2f}")

        # HedgeCoordinator handles the async execution
        # In live mode, this is processed asynchronously
        self._is_hedged = True
        self._entry_time = self.context.get_time()
        self._entry_funding_rate = funding_rate

    def _check_exit(self, symbol: str, price: float, funding_rate: float):
        """Close hedge when conditions are met."""
        should_exit = False
        reason = ""

        # 1. Funding rate normalized
        if funding_rate < self.exit_rate:
            should_exit = True
            reason = f"rate_normalized ({funding_rate*100:.4f}%)"

        # 2. Funding rate went negative (we'd be paying instead of receiving)
        if not should_exit and funding_rate < 0:
            should_exit = True
            reason = f"rate_negative ({funding_rate*100:.4f}%)"

        # 3. Max hold time
        if not should_exit and self.max_hold_hours > 0 and self._entry_time:
            elapsed = (self.context.get_time() - self._entry_time).total_seconds() / 3600
            if elapsed >= self.max_hold_hours:
                should_exit = True
                reason = f"max_hold ({elapsed:.1f}h)"

        if should_exit:
            self.context.log(f"[Hedge] CLOSE: {reason}")
            self._is_hedged = False
            self._entry_time = None
            # In live mode, HedgeCoordinator.close_hedge() is called by LiveManager

    def _check_entry_trigger(self, data: Dict[str, Any]) -> Optional[str]:
        """Not used — spot_futures_hedge uses its own on_data() flow."""
        return None

    def _check_additional_trigger(self, data: Dict[str, Any]) -> bool:
        """Not used — spot_futures_hedge manages positions directly."""
        return False

    @property
    def _log_prefix(self) -> str:
        return "SpotFuturesHedge"

    @property
    def _strategy_id(self) -> str:
        return "spot_futures_hedge"

    def get_state(self) -> Dict[str, Any]:
        state = super().get_state()
        state["is_hedged"] = self._is_hedged
        state["hedge_entry_time"] = self._entry_time.isoformat() if self._entry_time else None
        state["entry_funding_rate"] = self._entry_funding_rate
        state["total_funding_collected"] = self._total_funding_collected
        return state
