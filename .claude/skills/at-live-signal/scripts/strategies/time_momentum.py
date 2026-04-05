from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from .base import BaseStrategy, Side, customize_fields
from .martingale_base import MartingaleBase


class TimeMomentumStrategy(MartingaleBase):
    """
    Time Momentum Strategy (MartingaleBase-based):
    1. At start_time, capture daily reference price.
    2. At start_time + delay_minutes, snapshot check price change.
    3. If change >= target_percent => BUY (via MartingaleBase L1 entry).
    4. Position management (trailing stop, stop loss) handled by MartingaleBase.
    5. Force sell at stop_time (via _on_candle hook).
    6. One trade per day: checked_today guard.
    """

    PARAMETER_SCHEMA = {
        "fields": [
            # TimeMomentum-specific trigger parameters
            {"name": "start_time", "type": "time", "label": "Start Time",
             "default": "09:00",
             "description": "Time to start monitoring price",
             "show_in_table": True},
            {"name": "stop_time", "type": "time", "label": "Stop Time",
             "default": "15:00",
             "description": "Force exit time",
             "show_in_table": True},
            {"name": "delay_minutes", "type": "number", "label": "Delay (min)",
             "default": 10, "min": 0, "max": 120, "step": 1,
             "description": "Wait minutes after start before entry check",
             "show_in_table": True, "defaultOptRange": "5, 10, 30, 60"},
            {"name": "direction", "type": "select", "label": "Direction",
             "default": "rise", "options": ["rise", "fall"],
             "description": "rise=momentum buy, fall=dip buy",
             "show_in_table": True},
            {"name": "target_percent", "type": "number", "label": "Target (%)",
             "default": 2.0, "min": 0.1, "max": 20, "step": 0.1,
             "description": "Min price change % to trigger buy",
             "show_in_table": True, "defaultOptRange": "1.0, 2.0, 3.0, 5.0"},
        ] + customize_fields(BaseStrategy.COMMON_PARAMETER_FIELDS, {
            "max_buy_count": {"default": 1},
            "last_level_allin": {"default": "on"},
            "trailing_start_percent": {"default": 5.0, "defaultOptRange": "1.0, 3.0, 5.0, 10.0"},
            "trailing_stop_percent": {"default": 2.0, "defaultOptRange": "0.5, 1.0, 2.0, 3.0"},
            "max_loss_percent": {"default": 3.0, "defaultOptRange": "2.0, 3.0, 5.0"},
        })
    }

    def _initialize_trigger(self):
        """Initialize TimeMomentum-specific parameters and daily state."""
        self.start_time_str = self.config.get("start_time") or "09:00"
        self.stop_time_str = self.config.get("stop_time") or "15:00"

        try:
            self.start_time = datetime.strptime(self.start_time_str, "%H:%M").time()
        except ValueError:
            self.start_time = datetime.strptime("09:00", "%H:%M").time()

        try:
            self.stop_time = datetime.strptime(self.stop_time_str, "%H:%M").time()
        except ValueError:
            self.stop_time = datetime.strptime("15:00", "%H:%M").time()

        self.delay_minutes = int(self.config.get("delay_minutes", 10) or 10)
        self.direction = self.config.get("direction", "rise")

        raw_target = float(self.config.get("target_percent", 2.0) or 2.0)
        self.target_percent = abs(raw_target) / 100.0

        # Daily state
        self.checked_today = False
        self.daily_reference_price = None
        self._daily_date = None

        self.context.log(f"[{self._log_prefix}] Initialized: {self.direction} target={self.target_percent*100:.1f}% "
                         f"window={self.start_time_str}~{self.stop_time_str} delay={self.delay_minutes}min")

    def _on_candle(self, data: Dict[str, Any]):
        current_time = self.context.get_time()
        current_date = current_time.date()
        current_price = data['close']

        # 1. Daily reset
        if self._daily_date != current_date:
            self._daily_date = current_date
            self.checked_today = False
            self.daily_reference_price = None

        # 2. Capture daily reference price at start_time
        if current_time.time() >= self.start_time and self.daily_reference_price is None:
            self.daily_reference_price = current_price
            self.context.log(f"[{self._log_prefix}] Daily Reference: {self.daily_reference_price:,.0f} at {current_time.time()}")

        # 3. Stop time forced liquidation
        if self.current_level > 0 and current_time.time() >= self.stop_time:
            self.context.log(f"[{self._log_prefix}] STOP TIME {self.stop_time_str} reached. Force liquidation.")
            self._liquidate(current_price)
            self.checked_today = True

    def _check_entry_trigger(self, data: Dict[str, Any]) -> Optional[str]:
        if self.checked_today or self.daily_reference_price is None:
            return None

        current_time = self.context.get_time()
        trigger_time = datetime.combine(current_time.date(), self.start_time) + timedelta(minutes=self.delay_minutes)

        if current_time < trigger_time:
            return None

        self.checked_today = True

        current_price = data['close']
        change = (current_price - self.daily_reference_price) / self.daily_reference_price

        if self.direction == "fall":
            should_buy = change <= -self.target_percent
        else:
            should_buy = change >= self.target_percent

        if should_buy:
            self.context.log(f"[{self._log_prefix}] Entry TRIGGERED ({self.direction}): "
                             f"Change {change*100:.2f}% vs Target {self.target_percent*100:.2f}%")
        else:
            self.context.log(f"[{self._log_prefix}] Entry condition not met: "
                             f"Change {change*100:.2f}% vs Target {self.target_percent*100:.2f}% ({self.direction})")

        return Side.LONG if should_buy else None

    def _check_additional_trigger(self, data: Dict[str, Any]) -> bool:
        return False

    @property
    def _log_prefix(self) -> str:
        return "TimeMomentum"

    @property
    def _strategy_id(self) -> str:
        return "time_momentum"

    def get_state(self) -> Dict[str, Any]:
        state = super().get_state()

        change = 0
        if self.daily_reference_price and self.daily_reference_price > 0:
            current_price = self.context.get_current_price(self.config.get("symbol", ""))
            if current_price > 0:
                change = (current_price - self.daily_reference_price) / self.daily_reference_price

        current_time = self.context.get_time()
        trigger_time = datetime.combine(current_time.date(), self.start_time) + timedelta(minutes=self.delay_minutes)
        is_delay_passed = current_time >= trigger_time

        state["reference_price"] = self.daily_reference_price
        state["target_percent"] = self.target_percent
        state["direction"] = self.direction
        state["change_percent"] = change
        state["is_delay_passed"] = is_delay_passed
        state["has_bought"] = self.current_level > 0
        state["checked_today"] = self.checked_today
        state["start_time"] = self.start_time_str
        state["stop_time"] = self.stop_time_str
        state["delay_minutes"] = self.delay_minutes

        return state
