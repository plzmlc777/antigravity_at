from typing import Dict, Any
from collections import deque
from .base import BaseStrategy
from .martingale_base import MartingaleBase


class RsiMartingaleStrategy(MartingaleBase):
    """
    RSI Martingale Strategy
    - Buy trigger: RSI crosses below (or above) a trigger level.
    - Cooldown: After a trigger fires, no additional triggers until RSI
      crosses the reset level in the opposite direction.
    - All position management, trailing stop, HODL inherited from MartingaleBase.
    """

    PARAMETER_SCHEMA = {
        "fields": [
            # RSI-specific trigger parameters
            {"name": "rsi_period", "type": "number", "label": "RSI Period",
             "default": 14, "min": 2, "max": 100, "step": 1,
             "description": "Number of candles for RSI calculation",
             "show_in_table": True, "defaultOptRange": "7, 14, 21"},
            {"name": "trigger_level", "type": "number", "label": "Trigger RSI",
             "default": 30, "min": 1, "max": 99, "step": 1,
             "description": "RSI level that triggers a buy (e.g., 30 = oversold entry)",
             "show_in_table": True, "defaultOptRange": "20, 25, 30, 35"},
            {"name": "trigger_direction", "type": "select", "label": "Trigger Direction",
             "default": "below",
             "options": ["below", "above"],
             "description": "below = buy when RSI drops below trigger; above = buy when RSI rises above trigger",
             "show_in_table": True},
            {"name": "reset_level", "type": "number", "label": "Reset RSI",
             "default": 50, "min": 1, "max": 99, "step": 1,
             "description": "RSI must cross this level to re-arm the trigger (prevents consecutive buys)",
             "show_in_table": True, "defaultOptRange": "40, 50, 60, 70"},
            {"name": "reset_direction", "type": "select", "label": "Reset Direction",
             "default": "above",
             "options": ["above", "below"],
             "description": "above = trigger re-arms when RSI rises above reset; below = when RSI drops below reset",
             "show_in_table": True},
        ] + BaseStrategy.COMMON_PARAMETER_FIELDS
    }

    def _initialize_trigger(self):
        """Initialize RSI-specific state."""
        self.rsi_period = int(self.config.get("rsi_period", 14))
        self.trigger_level = float(self.config.get("trigger_level", 30))
        self.trigger_direction = self.config.get("trigger_direction", "below")
        self.reset_level = float(self.config.get("reset_level", 50))
        self.reset_direction = self.config.get("reset_direction", "above")

        # Price history for RSI calculation (need rsi_period + 1 closes)
        self._close_history = deque(maxlen=self.rsi_period + 1)
        self._prev_rsi = -1.0  # Previous RSI value for crossover detection
        self._current_rsi = -1.0
        self._trigger_armed = True  # Start armed (ready to fire)

    def preload_history(self, candles: list):
        """Preload close prices from historical candles for immediate RSI calculation."""
        needed = self.rsi_period + 2  # +2 to compute both prev and current RSI
        recent = candles[-needed:] if len(candles) >= needed else candles
        for candle in recent:
            close = candle.get('close', 0)
            if close > 0:
                self._prev_rsi = self._current_rsi
                self._close_history.append(close)
                self._current_rsi = self._calculate_rsi()
        if self._current_rsi >= 0:
            self.context.log(f"[{self._log_prefix}] RSI preloaded from history: {self._current_rsi:.2f} ({len(self._close_history)} candles)")

    def _calculate_rsi(self) -> float:
        """Calculate RSI from close price history. Returns -1 if not enough data."""
        if len(self._close_history) < self.rsi_period + 1:
            return -1.0

        gains = 0.0
        losses = 0.0
        prices = list(self._close_history)

        for i in range(1, len(prices)):
            change = prices[i] - prices[i - 1]
            if change > 0:
                gains += change
            else:
                losses += abs(change)

        avg_gain = gains / self.rsi_period
        avg_loss = losses / self.rsi_period

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def _on_candle(self, data: Dict[str, Any]):
        """Update RSI on every candle (called before any trigger logic)."""
        self._prev_rsi = self._current_rsi
        self._close_history.append(data['close'])
        self._current_rsi = self._calculate_rsi()

        # Always check reset condition (even when not in trigger check path)
        if not self._trigger_armed and self._prev_rsi >= 0 and self._current_rsi >= 0:
            if self._check_crossover(self._prev_rsi, self._current_rsi, self.reset_level, self.reset_direction):
                self._trigger_armed = True
                self.context.log(f"[{self._log_prefix}] Trigger RE-ARMED. RSI crossed {self.reset_direction} {self.reset_level} (RSI: {self._current_rsi:.1f})")

    def _check_crossover(self, prev: float, curr: float, level: float, direction: str) -> bool:
        """Check if RSI crossed a level in the given direction."""
        if direction == "below":
            return prev >= level and curr < level
        else:  # "above"
            return prev <= level and curr > level

    def _check_trigger_common(self) -> bool:
        """Shared trigger check for both L1 and L2+ entries."""
        if self._current_rsi < 0 or self._prev_rsi < 0:
            return False

        if not self._trigger_armed:
            return False

        if self._check_crossover(self._prev_rsi, self._current_rsi, self.trigger_level, self.trigger_direction):
            self._trigger_armed = False
            self.context.log(f"[{self._log_prefix}] BUY TRIGGER! RSI crossed {self.trigger_direction} {self.trigger_level} (RSI: {self._current_rsi:.1f})")
            return True

        return False

    def _check_entry_trigger(self, data: Dict[str, Any]) -> bool:
        """L1: RSI crosses trigger_level in trigger_direction."""
        return self._check_trigger_common()

    def _check_additional_trigger(self, data: Dict[str, Any]) -> bool:
        """L2+: Same RSI trigger logic (must re-arm between entries)."""
        return self._check_trigger_common()

    @property
    def _log_prefix(self) -> str:
        return "RsiMartingale"

    @property
    def _strategy_id(self) -> str:
        return "rsi_martingale"

    def get_state(self) -> Dict[str, Any]:
        state = super().get_state()
        state["current_rsi"] = round(self._current_rsi, 2) if self._current_rsi >= 0 else None
        state["trigger_armed"] = self._trigger_armed
        state["trigger_level"] = self.trigger_level
        state["reset_level"] = self.reset_level
        return state
