from typing import Dict, Any, Optional
from collections import deque
from .base import BaseStrategy
from .martingale_base import MartingaleBase
from app.core.constants import Side


class DonchianBreakoutStrategy(MartingaleBase):
    """
    Donchian Channel Breakout Strategy — Trend-following via N-period high/low channel.
    - Long entry: close breaks above the upper Donchian channel (N-period high).
    - Short entry: close breaks below the lower Donchian channel (N-period low).
    - Exit: price re-enters the shorter exit channel (opposite band).
    - All position management, trailing stop, martingale inherited from MartingaleBase.
    """

    PARAMETER_SCHEMA = {
        "fields": [
            {"name": "donchian_period", "type": "number", "label": "Donchian Period",
             "default": 20, "min": 5, "max": 200, "step": 1,
             "description": "N-period for entry channel (N-bar high/low)",
             "show_in_table": True, "defaultOptRange": "10, 20, 40, 55"},
            {"name": "exit_period", "type": "number", "label": "Exit Period",
             "default": 10, "min": 3, "max": 100, "step": 1,
             "description": "M-period for exit channel (shorter than entry period)",
             "show_in_table": True, "defaultOptRange": "5, 10, 20"},
        ] + BaseStrategy.COMMON_PARAMETER_FIELDS
    }

    def _initialize_trigger(self):
        self.donchian_period = int(self.config.get("donchian_period", 20))
        self.exit_period = int(self.config.get("exit_period", 10))
        self._high_history = deque(maxlen=self.donchian_period)
        self._low_history = deque(maxlen=self.donchian_period)
        self._exit_high_history = deque(maxlen=self.exit_period)
        self._exit_low_history = deque(maxlen=self.exit_period)
        self._upper_band = None
        self._lower_band = None
        self._exit_upper = None
        self._exit_lower = None
        self._prev_close = None
        self._upper_breakout = False
        self._lower_breakout = False
        self._trigger_armed = True

    def preload_history(self, candles: list):
        needed = self.donchian_period + 2
        recent = candles[-needed:] if len(candles) >= needed else candles
        for candle in recent:
            high = candle.get('high', 0)
            low = candle.get('low', 0)
            close = candle.get('close', 0)
            if high > 0 and low > 0 and close > 0:
                self._high_history.append(high)
                self._low_history.append(low)
                self._exit_high_history.append(high)
                self._exit_low_history.append(low)
                self._prev_close = close
        self._update_bands()
        if self._upper_band is not None:
            self.context.log(
                f"[{self._log_prefix}] Donchian preloaded: "
                f"upper={self._upper_band:.4f}, lower={self._lower_band:.4f} "
                f"(period={self.donchian_period}, {len(self._high_history)} candles)"
            )

    def _update_bands(self):
        if len(self._high_history) >= self.donchian_period:
            self._upper_band = max(self._high_history)
            self._lower_band = min(self._low_history)
        if len(self._exit_high_history) >= self.exit_period:
            self._exit_upper = max(self._exit_high_history)
            self._exit_lower = min(self._exit_low_history)

    def _on_candle(self, data: Dict[str, Any]):
        high = data['high']
        low = data['low']
        close = data['close']
        prev_upper = self._upper_band
        prev_lower = self._lower_band
        self._high_history.append(high)
        self._low_history.append(low)
        self._exit_high_history.append(high)
        self._exit_low_history.append(low)
        self._update_bands()
        self._upper_breakout = False
        self._lower_breakout = False
        if prev_upper is not None and self._prev_close is not None:
            if close > prev_upper:
                self._upper_breakout = True
            elif close < prev_lower:
                self._lower_breakout = True
        if not self._trigger_armed:
            if self._exit_upper is not None and self._exit_lower is not None:
                if self._exit_lower <= close <= self._exit_upper:
                    self._trigger_armed = True
                    self.context.log(
                        f"[{self._log_prefix}] Trigger RE-ARMED. "
                        f"close={close:.4f}, exit=[{self._exit_lower:.4f}, {self._exit_upper:.4f}]"
                    )
        self._prev_close = close

    def _check_entry_trigger(self, data: Dict[str, Any]) -> Optional[str]:
        if not self._trigger_armed or self._upper_band is None:
            return None
        if self._upper_breakout:
            self._trigger_armed = False
            self.context.log(
                f"[{self._log_prefix}] UPPER BREAKOUT! close={data['close']:.4f} > "
                f"channel_upper={self._upper_band:.4f} (period={self.donchian_period})"
            )
            return Side.LONG
        if self._lower_breakout:
            self._trigger_armed = False
            self.context.log(
                f"[{self._log_prefix}] LOWER BREAKOUT! close={data['close']:.4f} < "
                f"channel_lower={self._lower_band:.4f} (period={self.donchian_period})"
            )
            return Side.SHORT
        return None

    def _check_additional_trigger(self, data: Dict[str, Any]) -> bool:
        if not self._upper_breakout or not self._trigger_armed:
            return False
        self._trigger_armed = False
        self.context.log(f"[{self._log_prefix}] Additional UPPER BREAKOUT! close={data['close']:.4f}")
        return True

    def _check_exit_trigger(self, data: Dict[str, Any]) -> bool:
        if self._exit_lower is None or self._exit_upper is None:
            return False
        close = data['close']
        if self.is_short:
            if close >= self._exit_upper:
                self.context.log(f"[{self._log_prefix}] EXIT SHORT: close={close:.4f} >= exit_upper={self._exit_upper:.4f}")
                return True
        else:
            if close <= self._exit_lower:
                self.context.log(f"[{self._log_prefix}] EXIT LONG: close={close:.4f} <= exit_lower={self._exit_lower:.4f}")
                return True
        return False

    @property
    def _log_prefix(self) -> str:
        return "DonchianBreakout"

    @property
    def _strategy_id(self) -> str:
        return "donchian_breakout"

    def get_state(self) -> Dict[str, Any]:
        state = super().get_state()
        state["donchian_period"] = self.donchian_period
        state["exit_period"] = self.exit_period
        state["upper_band"] = round(self._upper_band, 4) if self._upper_band is not None else None
        state["lower_band"] = round(self._lower_band, 4) if self._lower_band is not None else None
        state["exit_upper"] = round(self._exit_upper, 4) if self._exit_upper is not None else None
        state["exit_lower"] = round(self._exit_lower, 4) if self._exit_lower is not None else None
        state["upper_breakout"] = self._upper_breakout
        state["lower_breakout"] = self._lower_breakout
        state["trigger_armed"] = self._trigger_armed
        return state
