"""
US Market Follow Strategy (미장 연계 일일 매매)

Entry: Buy when US market (S&P 500 / NASDAQ) changed >= N% on previous close.
Exit:  Trailing stop or cycle time limit (inherited from MartingaleBase).
Mode:  Single entry (max_levels=1 recommended).

Strategy Request ID: 8eb64b61-b5af-4e22-84f7-e67790c18ed9
"""
from typing import Dict, Any
from .base import BaseStrategy, customize_fields
from .martingale_base import MartingaleBase


class USMarketFollowStrategy(MartingaleBase):
    """
    Buys Korean stocks based on previous US market performance.
    - Check US market close-to-close change at Korean market open.
    - If change >= threshold → buy.
    - One entry per day (trigger resets daily).
    - Exit via trailing stop or cycle_max_hours.
    """

    PARAMETER_SCHEMA = {
        "fields": [
            {"name": "us_index", "type": "combobox", "label": "US Index / Ticker",
             "default": "^GSPC",
             "options": [
                 {"value": "^GSPC", "label": "^GSPC (S&P 500)"},
                 {"value": "^IXIC", "label": "^IXIC (NASDAQ)"},
                 {"value": "^DJI", "label": "^DJI (Dow Jones)"},
                 {"value": "^SOX", "label": "^SOX (Semiconductor)"},
             ],
             "placeholder": "e.g. ^GSPC, AAPL, NVDA",
             "description": "US index or stock ticker (yfinance). Presets: ^GSPC, ^IXIC, ^DJI, ^SOX. Or type any ticker.",
             "show_in_table": True},
            {"name": "us_threshold", "type": "number", "label": "US Change Threshold (%)",
             "default": 0.5, "min": -10, "max": 10, "step": 0.1,
             "description": "Minimum US market change % to trigger buy (e.g., 0.5 = buy when US up 0.5%+)",
             "show_in_table": True, "defaultOptRange": "0.3, 0.5, 1.0, 1.5, 2.0"},
            {"name": "us_direction", "type": "select", "label": "Follow Direction",
             "default": "rise",
             "options": ["rise", "fall"],
             "description": "rise = buy when US goes up; fall = buy when US goes down",
             "show_in_table": True},
        ] + customize_fields(BaseStrategy.COMMON_PARAMETER_FIELDS, {
            "max_buy_count": {"default": 1},
        })
    }

    def _initialize_trigger(self):
        """Initialize US market data."""
        self.us_index = self.config.get("us_index", "^GSPC")
        self.us_threshold = float(self.config.get("us_threshold", 0.5))
        self.us_direction = self.config.get("us_direction", "rise")

        # Daily tracking
        self._last_checked_date = None
        self._today_us_change = None
        self._today_triggered = False

        # Backtest: preload US market history
        self._us_change_map = None

    def _load_us_change_map(self):
        """Lazy-load US market change map for backtesting."""
        if self._us_change_map is not None:
            return

        try:
            from ..core.us_market_data import us_market
            self._us_change_map = us_market.get_change_map(self.us_index, days=730)
            self.context.log(f"[{self._log_prefix}] Loaded US market history: {len(self._us_change_map)} trading days")
        except Exception as e:
            self.context.log(f"[{self._log_prefix}] Failed to load US market data: {e}")
            self._us_change_map = {}

    def _get_us_change_for_today(self) -> float:
        """Get US market change relevant for today's Korean trading session."""
        current_time = self.context.get_time()
        current_date = str(current_time.date())

        # Already checked today
        if self._last_checked_date == current_date and self._today_us_change is not None:
            return self._today_us_change

        self._last_checked_date = current_date

        # Load change map if needed
        self._load_us_change_map()

        if self._us_change_map:
            # Backtest or cached: lookup by date
            from ..core.us_market_data import us_market
            self._today_us_change = us_market.get_change_for_date(current_date, self._us_change_map)
        else:
            # Live fallback: get latest change
            try:
                from ..core.us_market_data import us_market
                change = us_market.get_change(self.us_index)
                self._today_us_change = change if change is not None else 0.0
            except Exception:
                self._today_us_change = 0.0

        return self._today_us_change

    def _on_candle(self, data: Dict[str, Any]):
        """Reset trigger on new day."""
        current_date = str(self.context.get_time().date())
        if self._last_checked_date != current_date:
            self._today_triggered = False
            self._today_us_change = None

    def _check_entry_trigger(self, data: Dict[str, Any]) -> bool:
        """L1: Buy if US market change meets threshold."""
        if self._today_triggered:
            return False

        us_change = self._get_us_change_for_today()

        if self.us_direction == "rise":
            triggered = us_change >= self.us_threshold
        else:  # "fall"
            triggered = us_change <= -self.us_threshold

        if triggered:
            self._today_triggered = True
            direction_str = "UP" if self.us_direction == "rise" else "DOWN"
            self.context.log(
                f"[{self._log_prefix}] BUY TRIGGER! US({self.us_index}) {direction_str} {us_change:+.2f}% "
                f">= threshold {self.us_threshold}%"
            )
            return True

        return False

    def _check_additional_trigger(self, data: Dict[str, Any]) -> bool:
        """L2+: Same logic (for multi-level if desired)."""
        return self._check_entry_trigger(data)

    @property
    def _log_prefix(self) -> str:
        return "USFollow"

    @property
    def _strategy_id(self) -> str:
        return "us_market_follow"

    def get_state(self) -> Dict[str, Any]:
        state = super().get_state()
        state["us_index"] = self.us_index
        state["us_threshold"] = self.us_threshold
        state["us_direction"] = self.us_direction
        state["today_us_change"] = self._today_us_change
        state["today_triggered"] = self._today_triggered
        return state
