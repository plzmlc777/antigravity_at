from typing import Dict, Any, Optional
from collections import deque
from .base import BaseStrategy
from .martingale_base import MartingaleBase
from app.core.constants import Side


class RsiMartingaleStrategy(MartingaleBase):
    """
    RSI Martingale Strategy
    - LONG trigger: RSI crosses below oversold level (e.g., 30)
    - SHORT trigger: RSI crosses above overbought level (e.g., 70)
    - Cooldown: After a trigger fires, no additional triggers until RSI
      crosses the reset level in the opposite direction.
    - position_side="long": only LONG triggers active
    - position_side="short": only SHORT triggers active
    - position_side="both": both LONG and SHORT triggers active independently
    - All position management, trailing stop, HODL inherited from MartingaleBase.
    """

    PARAMETER_SCHEMA = {
        "fields": [
            # RSI-specific trigger parameters
            {"name": "rsi_period", "type": "number", "label": "RSI Period",
             "default": 14, "min": 2, "max": 100, "step": 1,
             "description": "Number of candles for RSI calculation",
             "show_in_table": True, "defaultOptRange": "7, 14, 21"},
            # ── LONG entry trigger ── (visible when position_side is "long" or "both")
            {"name": "trigger_level", "type": "number", "label": "Trigger RSI",
             "default": 30, "min": 1, "max": 99, "step": 1,
             "description": "RSI level that triggers LONG entry (e.g., 30 = oversold → buy)",
             "group": "long_trigger",
             "show_in_table": True, "defaultOptRange": "20, 25, 30, 35",
             "visible_when": {"position_side": {"ne": "short"}}},
            {"name": "trigger_direction", "type": "select", "label": "Trigger Dir",
             "default": "below",
             "options": ["below", "above"],
             "description": "below = LONG when RSI drops below trigger; above = LONG when RSI rises above",
             "group": "long_trigger",
             "show_in_table": False,
             "visible_when": {"position_side": {"ne": "short"}}},
            {"name": "reset_level", "type": "number", "label": "Reset RSI",
             "default": 50, "min": 1, "max": 99, "step": 1,
             "description": "RSI must cross this level to re-arm LONG trigger",
             "group": "long_trigger",
             "show_in_table": False, "defaultOptRange": "40, 50, 60, 70",
             "visible_when": {"position_side": {"ne": "short"}}},
            {"name": "reset_direction", "type": "select", "label": "Reset Dir",
             "default": "above",
             "options": ["above", "below"],
             "description": "Direction RSI must cross to re-arm LONG trigger",
             "group": "long_trigger",
             "show_in_table": False,
             "visible_when": {"position_side": {"ne": "short"}}},
            # ── SHORT entry trigger ── (visible when position_side is "short" or "both")
            {"name": "short_trigger_level", "type": "number", "label": "Trigger RSI",
             "default": 70, "min": 1, "max": 99, "step": 1,
             "description": "RSI level that triggers SHORT entry (e.g., 70 = overbought → short)",
             "group": "short_trigger",
             "show_in_table": True, "defaultOptRange": "65, 70, 75, 80",
             "visible_when": {"position_side": {"ne": "long"}}},
            {"name": "short_trigger_direction", "type": "select", "label": "Trigger Dir",
             "default": "above",
             "options": ["below", "above"],
             "description": "above = SHORT when RSI rises above trigger; below = SHORT when RSI drops below",
             "group": "short_trigger",
             "show_in_table": False,
             "visible_when": {"position_side": {"ne": "long"}}},
            {"name": "short_reset_level", "type": "number", "label": "Reset RSI",
             "default": 50, "min": 1, "max": 99, "step": 1,
             "description": "RSI must cross this level to re-arm SHORT trigger",
             "group": "short_trigger",
             "show_in_table": False, "defaultOptRange": "30, 40, 50, 60",
             "visible_when": {"position_side": {"ne": "long"}}},
            {"name": "short_reset_direction", "type": "select", "label": "Reset Dir",
             "default": "below",
             "options": ["above", "below"],
             "description": "Direction RSI must cross to re-arm SHORT trigger",
             "group": "short_trigger",
             "show_in_table": False,
             "visible_when": {"position_side": {"ne": "long"}}},
        ] + BaseStrategy.COMMON_PARAMETER_FIELDS
    }

    def _initialize_trigger(self):
        """Initialize RSI-specific state."""
        self.rsi_period = int(self.config.get("rsi_period", 14))

        # LONG trigger params (backward compatible with existing configs)
        self.trigger_level = float(self.config.get("trigger_level", 30))
        self.trigger_direction = self.config.get("trigger_direction", "below")
        self.reset_level = float(self.config.get("reset_level", 50))
        self.reset_direction = self.config.get("reset_direction", "above")

        # SHORT trigger params
        self.short_trigger_level = float(self.config.get("short_trigger_level", 70))
        self.short_trigger_direction = self.config.get("short_trigger_direction", "above")
        self.short_reset_level = float(self.config.get("short_reset_level", 50))
        self.short_reset_direction = self.config.get("short_reset_direction", "below")

        # Price history for RSI calculation (need rsi_period + 1 closes)
        self._close_history = deque(maxlen=self.rsi_period + 1)
        self._prev_rsi = -1.0  # Previous RSI value for crossover detection
        self._current_rsi = -1.0

        # Independent trigger arming for LONG and SHORT
        self._long_trigger_armed = True
        self._short_trigger_armed = True

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

        if self._prev_rsi < 0 or self._current_rsi < 0:
            return

        # RSI tracking log for comparison testing
        self.context.log(f"[{self._log_prefix}] RSI: {self._current_rsi:.2f} (prev={self._prev_rsi:.2f}) armed={self._long_trigger_armed} trigger={self.trigger_level}")

        # Check LONG reset condition
        if not self._long_trigger_armed:
            if self._check_crossover(self._prev_rsi, self._current_rsi, self.reset_level, self.reset_direction):
                self._long_trigger_armed = True
                self.context.log(f"[{self._log_prefix}] LONG Trigger RE-ARMED. RSI crossed {self.reset_direction} {self.reset_level} (RSI: {self._current_rsi:.1f})")

        # Check SHORT reset condition
        if not self._short_trigger_armed:
            if self._check_crossover(self._prev_rsi, self._current_rsi, self.short_reset_level, self.short_reset_direction):
                self._short_trigger_armed = True
                self.context.log(f"[{self._log_prefix}] SHORT Trigger RE-ARMED. RSI crossed {self.short_reset_direction} {self.short_reset_level} (RSI: {self._current_rsi:.1f})")

    def _check_crossover(self, prev: float, curr: float, level: float, direction: str) -> bool:
        """Check if RSI crossed a level in the given direction."""
        if direction == "below":
            return prev >= level and curr < level
        else:  # "above"
            return prev <= level and curr > level

    def _check_entry_trigger(self, data: Dict[str, Any]) -> Optional[str]:
        """L1: Check both LONG and SHORT RSI triggers independently."""
        if self._current_rsi < 0 or self._prev_rsi < 0:
            return None

        # Check LONG trigger
        if self._long_trigger_armed:
            if self._check_crossover(self._prev_rsi, self._current_rsi, self.trigger_level, self.trigger_direction):
                self._long_trigger_armed = False
                self.context.log(f"[{self._log_prefix}] LONG TRIGGER! RSI crossed {self.trigger_direction} {self.trigger_level} (RSI: {self._current_rsi:.1f})")
                return Side.LONG

        # Check SHORT trigger
        if self._short_trigger_armed:
            if self._check_crossover(self._prev_rsi, self._current_rsi, self.short_trigger_level, self.short_trigger_direction):
                self._short_trigger_armed = False
                self.context.log(f"[{self._log_prefix}] SHORT TRIGGER! RSI crossed {self.short_trigger_direction} {self.short_trigger_level} (RSI: {self._current_rsi:.1f})")
                return Side.SHORT

        return None

    def _check_additional_trigger(self, data: Dict[str, Any]) -> bool:
        """L2+: Same direction trigger as current position (must re-arm between entries)."""
        if self._current_rsi < 0 or self._prev_rsi < 0:
            return False

        if self.is_short:
            # SHORT additional: use short trigger params
            if not self._short_trigger_armed:
                return False
            if self._check_crossover(self._prev_rsi, self._current_rsi, self.short_trigger_level, self.short_trigger_direction):
                self._short_trigger_armed = False
                self.context.log(f"[{self._log_prefix}] SHORT ADD TRIGGER! RSI crossed {self.short_trigger_direction} {self.short_trigger_level} (RSI: {self._current_rsi:.1f})")
                return True
        else:
            # LONG additional: use long trigger params
            if not self._long_trigger_armed:
                return False
            if self._check_crossover(self._prev_rsi, self._current_rsi, self.trigger_level, self.trigger_direction):
                self._long_trigger_armed = False
                self.context.log(f"[{self._log_prefix}] LONG ADD TRIGGER! RSI crossed {self.trigger_direction} {self.trigger_level} (RSI: {self._current_rsi:.1f})")
                return True

        return False

    @property
    def _log_prefix(self) -> str:
        return "RsiMartingale"

    @property
    def _strategy_id(self) -> str:
        return "rsi_martingale"

    def get_state(self) -> Dict[str, Any]:
        state = super().get_state()
        state["current_rsi"] = round(self._current_rsi, 2) if self._current_rsi >= 0 else None
        state["long_trigger_armed"] = self._long_trigger_armed
        state["short_trigger_armed"] = self._short_trigger_armed
        state["trigger_level"] = self.trigger_level
        state["short_trigger_level"] = self.short_trigger_level
        state["reset_level"] = self.reset_level
        state["short_reset_level"] = self.short_reset_level
        return state
