from typing import Dict, Any, Optional
from collections import deque
from .base import BaseStrategy
from .martingale_base import MartingaleBase
from app.core.constants import Side


class MacdMomentumStrategy(MartingaleBase):
    """
    MACD Momentum Strategy — Trend-following using MACD histogram or signal-line cross.

    Two entry modes:
    - histogram_cross (default): histogram crosses above/below zero.
    - signal_cross: MACD line crosses the signal line.

    histogram_threshold filters weak crosses. Exit on opposite cross.
    All position management, trailing stop, martingale inherited from MartingaleBase.
    """

    PARAMETER_SCHEMA = {
        "fields": [
            {"name": "macd_fast", "type": "number", "label": "MACD Fast Period",
             "default": 12, "min": 2, "max": 100, "step": 1,
             "description": "Fast EMA period for MACD line",
             "show_in_table": True, "defaultOptRange": "8, 12, 16, 20"},
            {"name": "macd_slow", "type": "number", "label": "MACD Slow Period",
             "default": 26, "min": 5, "max": 200, "step": 1,
             "description": "Slow EMA period for MACD line",
             "show_in_table": True, "defaultOptRange": "20, 26, 34, 50"},
            {"name": "macd_signal", "type": "number", "label": "Signal Period",
             "default": 9, "min": 2, "max": 50, "step": 1,
             "description": "EMA period for MACD signal line",
             "show_in_table": True, "defaultOptRange": "6, 9, 12"},
            {"name": "histogram_threshold", "type": "number", "label": "Histogram Threshold",
             "default": 0.0, "min": 0.0, "max": 10.0, "step": 0.1,
             "description": "Minimum absolute histogram value at cross (noise filter)",
             "show_in_table": False},
            {"name": "entry_mode", "type": "select",
             "options": ["histogram_cross", "signal_cross"],
             "label": "Entry Mode",
             "default": "histogram_cross",
             "description": "histogram_cross: histogram zero-cross; signal_cross: MACD/signal-line cross",
             "show_in_table": False},
        ] + BaseStrategy.COMMON_PARAMETER_FIELDS
    }

    def _initialize_trigger(self):
        self.macd_fast = int(self.config.get("macd_fast", 12))
        self.macd_slow = int(self.config.get("macd_slow", 26))
        self.macd_signal_period = int(self.config.get("macd_signal", 9))
        self.histogram_threshold = float(self.config.get("histogram_threshold", 0.0))
        self.entry_mode = str(self.config.get("entry_mode", "histogram_cross"))

        warmup = max(self.macd_fast, self.macd_slow) + self.macd_signal_period + 1
        self._close_history = deque(maxlen=warmup + 2)

        self._fast_k = 2.0 / (self.macd_fast + 1)
        self._slow_k = 2.0 / (self.macd_slow + 1)
        self._sig_k = 2.0 / (self.macd_signal_period + 1)

        self._ema_fast = None
        self._ema_slow = None
        self._ema_signal = None

        self._prev_histogram = None
        self._prev_macd_line = None
        self._prev_signal_val = None

        self._histogram = None
        self._macd_line = None

        self._bull_cross = False
        self._bear_cross = False
        self._trigger_armed = True

    def preload_history(self, candles: list):
        warmup = max(self.macd_fast, self.macd_slow) + self.macd_signal_period + 2
        recent = candles[-warmup:] if len(candles) >= warmup else candles
        for candle in recent:
            close = candle.get("close", 0)
            if close > 0:
                self._close_history.append(close)
                self._update_macd(close)
        if self._ema_signal is not None:
            self.context.log(
                f"[MacdMomentum] preloaded: MACD={self._macd_line:.6f} "
                f"signal={self._ema_signal:.6f} hist={self._histogram:.6f} "
                f"({len(self._close_history)} candles)"
            )

    def _calc_ema(self, prev, close, k):
        period = round(2.0 / k - 1)
        count = len(self._close_history)
        if count < period:
            return None
        if prev is None:
            return sum(list(self._close_history)[-period:]) / period
        return prev + k * (close - prev)

    def _update_macd(self, close: float):
        self._ema_fast = self._calc_ema(self._ema_fast, close, self._fast_k)
        self._ema_slow = self._calc_ema(self._ema_slow, close, self._slow_k)
        if self._ema_fast is None or self._ema_slow is None:
            self._macd_line = None
            self._ema_signal = None
            self._histogram = None
            return
        new_macd = self._ema_fast - self._ema_slow
        if self._ema_signal is None:
            self._ema_signal = new_macd
        else:
            self._ema_signal = self._ema_signal + self._sig_k * (new_macd - self._ema_signal)
        self._macd_line = new_macd
        self._histogram = new_macd - self._ema_signal

    def _detect_crosses(self):
        self._bull_cross = False
        self._bear_cross = False
        if self.entry_mode == "histogram_cross":
            if self._histogram is None or self._prev_histogram is None:
                return
            if self._prev_histogram <= 0 and self._histogram > 0:
                if abs(self._histogram) >= self.histogram_threshold:
                    self._bull_cross = True
            if self._prev_histogram >= 0 and self._histogram < 0:
                if abs(self._histogram) >= self.histogram_threshold:
                    self._bear_cross = True
        else:
            if (self._macd_line is None or self._ema_signal is None
                    or self._prev_macd_line is None or self._prev_signal_val is None):
                return
            prev_diff = self._prev_macd_line - self._prev_signal_val
            curr_diff = self._macd_line - self._ema_signal
            if prev_diff <= 0 and curr_diff > 0:
                if abs(curr_diff) >= self.histogram_threshold:
                    self._bull_cross = True
            if prev_diff >= 0 and curr_diff < 0:
                if abs(curr_diff) >= self.histogram_threshold:
                    self._bear_cross = True

    def _on_candle(self, data: Dict[str, Any]):
        close = data["close"]
        self._prev_histogram = self._histogram
        self._prev_macd_line = self._macd_line
        self._prev_signal_val = self._ema_signal
        self._close_history.append(close)
        self._update_macd(close)
        self._detect_crosses()
        if not self._trigger_armed:
            if self._bull_cross or self._bear_cross:
                self._trigger_armed = True
                cross_type = "bull" if self._bull_cross else "bear"
                self.context.log(
                    f"[MacdMomentum] Trigger RE-ARMED ({cross_type}). hist={self._histogram:.6f}"
                )

    def _check_entry_trigger(self, data: Dict[str, Any]) -> Optional[str]:
        if not self._trigger_armed or self._histogram is None:
            return None
        if self._bull_cross:
            self._trigger_armed = False
            self.context.log(
                f"[MacdMomentum] BULL CROSS -> LONG. hist={self._histogram:.6f}"
            )
            return Side.LONG
        if self._bear_cross:
            self._trigger_armed = False
            self.context.log(
                f"[MacdMomentum] BEAR CROSS -> SHORT. hist={self._histogram:.6f}"
            )
            return Side.SHORT
        return None

    def _check_additional_trigger(self, data: Dict[str, Any]) -> bool:
        if not self._bull_cross or not self._trigger_armed:
            return False
        self._trigger_armed = False
        self.context.log(f"[MacdMomentum] Additional BULL CROSS. hist={self._histogram:.6f}")
        return True

    def _check_exit_trigger(self, data: Dict[str, Any]) -> bool:
        if self.is_short:
            if not self._bull_cross:
                return False
            self.context.log(f"[MacdMomentum] BULL CROSS -> Cover SHORT.")
            return True
        else:
            if not self._bear_cross:
                return False
            self.context.log(f"[MacdMomentum] BEAR CROSS -> Sell LONG.")
            return True

    @property
    def _log_prefix(self) -> str:
        return "MacdMomentum"

    @property
    def _strategy_id(self) -> str:
        return "macd_momentum"

    def get_state(self) -> Dict[str, Any]:
        state = super().get_state()
        state["macd_line"] = round(self._macd_line, 6) if self._macd_line is not None else None
        state["signal"] = round(self._ema_signal, 6) if self._ema_signal is not None else None
        state["histogram"] = round(self._histogram, 6) if self._histogram is not None else None
        state["bull_cross"] = self._bull_cross
        state["bear_cross"] = self._bear_cross
        state["trigger_armed"] = self._trigger_armed
        state["entry_mode"] = self.entry_mode
        return state
