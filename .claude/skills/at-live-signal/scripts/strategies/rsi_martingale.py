"""
RSI Martingale Strategy — 스킬 폴더 독립 실행 버전.

backend/app/strategies/rsi_martingale.py 와 100% 동일한 로직.
import 경로만 로컬 strategies 패키지로 변경.
"""

from typing import Dict, Any, Optional
from collections import deque
from .base import BaseStrategy, Side
from .martingale_base import MartingaleBase


class RsiMartingaleStrategy(MartingaleBase):
    """
    RSI Martingale Strategy
    - LONG trigger: RSI crosses below oversold level (e.g., 30)
    - SHORT trigger: RSI crosses above overbought level (e.g., 70)
    - Cooldown: After a trigger fires, no additional triggers until RSI
      crosses the reset level in the opposite direction.
    """

    PARAMETER_SCHEMA = {
        "fields": [
            {"name": "rsi_period", "type": "number", "label": "RSI Period",
             "default": 14, "min": 2, "max": 100, "step": 1,
             "description": "Number of candles for RSI calculation",
             "show_in_table": True, "defaultOptRange": "7, 14, 21"},
            # ── LONG entry trigger ──
            {"name": "trigger_level", "type": "number", "label": "Trigger RSI",
             "default": 30, "min": 1, "max": 99, "step": 1,
             "description": "RSI level that triggers LONG entry",
             "group": "long_trigger", "show_in_table": True,
             "defaultOptRange": "20, 25, 30, 35",
             "visible_when": {"position_side": {"ne": "short"}}},
            {"name": "trigger_direction", "type": "select", "label": "Trigger Dir",
             "default": "below", "options": ["below", "above"],
             "description": "below = LONG when RSI drops below trigger",
             "group": "long_trigger", "show_in_table": False,
             "visible_when": {"position_side": {"ne": "short"}}},
            {"name": "reset_level", "type": "number", "label": "Reset RSI",
             "default": 50, "min": 1, "max": 99, "step": 1,
             "description": "RSI must cross this level to re-arm LONG trigger",
             "group": "long_trigger", "show_in_table": False,
             "defaultOptRange": "40, 50, 60, 70",
             "visible_when": {"position_side": {"ne": "short"}}},
            {"name": "reset_direction", "type": "select", "label": "Reset Dir",
             "default": "above", "options": ["above", "below"],
             "group": "long_trigger", "show_in_table": False,
             "visible_when": {"position_side": {"ne": "short"}}},
            # ── SHORT entry trigger ──
            {"name": "short_trigger_level", "type": "number", "label": "Trigger RSI",
             "default": 70, "min": 1, "max": 99, "step": 1,
             "description": "RSI level that triggers SHORT entry",
             "group": "short_trigger", "show_in_table": True,
             "defaultOptRange": "65, 70, 75, 80",
             "visible_when": {"position_side": {"ne": "long"}}},
            {"name": "short_trigger_direction", "type": "select", "label": "Trigger Dir",
             "default": "above", "options": ["below", "above"],
             "group": "short_trigger", "show_in_table": False,
             "visible_when": {"position_side": {"ne": "long"}}},
            {"name": "short_reset_level", "type": "number", "label": "Reset RSI",
             "default": 50, "min": 1, "max": 99, "step": 1,
             "group": "short_trigger", "show_in_table": False,
             "defaultOptRange": "30, 40, 50, 60",
             "visible_when": {"position_side": {"ne": "long"}}},
            {"name": "short_reset_direction", "type": "select", "label": "Reset Dir",
             "default": "below", "options": ["above", "below"],
             "group": "short_trigger", "show_in_table": False,
             "visible_when": {"position_side": {"ne": "long"}}},
        ] + BaseStrategy.COMMON_PARAMETER_FIELDS
    }

    def _initialize_trigger(self):
        self.rsi_period = int(self.config.get("rsi_period", 14))
        self.trigger_level = float(self.config.get("trigger_level", 30))
        self.trigger_direction = self.config.get("trigger_direction", "below")
        self.reset_level = float(self.config.get("reset_level", 50))
        self.reset_direction = self.config.get("reset_direction", "above")
        self.short_trigger_level = float(self.config.get("short_trigger_level", 70))
        self.short_trigger_direction = self.config.get("short_trigger_direction", "above")
        self.short_reset_level = float(self.config.get("short_reset_level", 50))
        self.short_reset_direction = self.config.get("short_reset_direction", "below")
        self._close_history = deque(maxlen=self.rsi_period + 1)
        self._prev_rsi = -1.0
        self._current_rsi = -1.0
        self._long_trigger_armed = True
        self._short_trigger_armed = True

    def preload_history(self, candles: list):
        needed = self.rsi_period + 2
        recent = candles[-needed:] if len(candles) >= needed else candles
        for candle in recent:
            close = candle.get('close', 0)
            if close > 0:
                self._prev_rsi = self._current_rsi
                self._close_history.append(close)
                self._current_rsi = self._calculate_rsi()

    def _calculate_rsi(self) -> float:
        if len(self._close_history) < self.rsi_period + 1:
            return -1.0
        gains, losses = 0.0, 0.0
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
        self._prev_rsi = self._current_rsi
        self._close_history.append(data['close'])
        self._current_rsi = self._calculate_rsi()
        if self._prev_rsi < 0 or self._current_rsi < 0:
            return
        # Check reset conditions
        if not self._long_trigger_armed:
            if self._check_crossover(self._prev_rsi, self._current_rsi, self.reset_level, self.reset_direction):
                self._long_trigger_armed = True
        if not self._short_trigger_armed:
            if self._check_crossover(self._prev_rsi, self._current_rsi, self.short_reset_level, self.short_reset_direction):
                self._short_trigger_armed = True

    def _check_crossover(self, prev: float, curr: float, level: float, direction: str) -> bool:
        if direction == "below":
            return prev >= level and curr < level
        else:
            return prev <= level and curr > level

    def _check_entry_trigger(self, data: Dict[str, Any]) -> Optional[str]:
        if self._current_rsi < 0 or self._prev_rsi < 0:
            return None
        if self._long_trigger_armed:
            if self._check_crossover(self._prev_rsi, self._current_rsi, self.trigger_level, self.trigger_direction):
                self._long_trigger_armed = False
                return Side.LONG
        if self._short_trigger_armed:
            if self._check_crossover(self._prev_rsi, self._current_rsi, self.short_trigger_level, self.short_trigger_direction):
                self._short_trigger_armed = False
                return Side.SHORT
        return None

    def _check_additional_trigger(self, data: Dict[str, Any]) -> bool:
        if self._current_rsi < 0 or self._prev_rsi < 0:
            return False
        if self.is_short:
            if not self._short_trigger_armed:
                return False
            if self._check_crossover(self._prev_rsi, self._current_rsi, self.short_trigger_level, self.short_trigger_direction):
                self._short_trigger_armed = False
                return True
        else:
            if not self._long_trigger_armed:
                return False
            if self._check_crossover(self._prev_rsi, self._current_rsi, self.trigger_level, self.trigger_direction):
                self._long_trigger_armed = False
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
        return state
