from typing import Dict, Any, Optional
from collections import deque
from .base import BaseStrategy
from .martingale_base import MartingaleBase
from ..core.constants import Side


class EmaMomentumStrategy(MartingaleBase):
    """
    EMA Momentum Strategy — Trend-following using EMA crossover.
    - Buy trigger: EMA(fast) crosses above EMA(slow) (golden cross).
    - Exit trigger: EMA(fast) crosses below EMA(slow) (dead cross).
    - All position management, trailing stop, martingale inherited from MartingaleBase.
    """

    PARAMETER_SCHEMA = {
        "fields": [
            {"name": "ema_fast_period", "type": "number", "label": "EMA Fast Period",
             "default": 9, "min": 2, "max": 200, "step": 1,
             "description": "Short-term EMA period (faster signal line)",
             "show_in_table": True, "defaultOptRange": "5, 9, 12, 20"},
            {"name": "ema_slow_period", "type": "number", "label": "EMA Slow Period",
             "default": 21, "min": 5, "max": 500, "step": 1,
             "description": "Long-term EMA period (slower trend line)",
             "show_in_table": True, "defaultOptRange": "21, 50, 100, 200"},
        ] + BaseStrategy.COMMON_PARAMETER_FIELDS
    }

    def _initialize_trigger(self):
        """Initialize EMA-specific state."""
        self.ema_fast_period = int(self.config.get("ema_fast_period", 9))
        self.ema_slow_period = int(self.config.get("ema_slow_period", 21))

        # Need enough history for the slower EMA
        max_period = max(self.ema_fast_period, self.ema_slow_period)
        self._close_history = deque(maxlen=max_period + 1)

        # EMA values
        self._ema_fast = None
        self._ema_slow = None
        self._prev_ema_fast = None
        self._prev_ema_slow = None

        # EMA smoothing factors
        self._fast_factor = 2.0 / (self.ema_fast_period + 1)
        self._slow_factor = 2.0 / (self.ema_slow_period + 1)

        # Crossover state
        self._golden_cross = False  # fast crossed above slow
        self._dead_cross = False    # fast crossed below slow
        self._trigger_armed = True  # ready to fire entry

    def preload_history(self, candles: list):
        """Preload close prices from historical candles for EMA warmup."""
        max_period = max(self.ema_fast_period, self.ema_slow_period)
        needed = max_period + 2  # +2 for prev/current crossover detection
        recent = candles[-needed:] if len(candles) >= needed else candles

        for candle in recent:
            close = candle.get('close', 0)
            if close > 0:
                self._prev_ema_fast = self._ema_fast
                self._prev_ema_slow = self._ema_slow
                self._close_history.append(close)
                self._update_emas(close)

        if self._ema_fast is not None and self._ema_slow is not None:
            self.context.log(
                f"[{self._log_prefix}] EMA preloaded: "
                f"fast({self.ema_fast_period})={self._ema_fast:.4f}, "
                f"slow({self.ema_slow_period})={self._ema_slow:.4f} "
                f"({len(self._close_history)} candles)"
            )

    def _update_emas(self, close: float):
        """Update both EMA values incrementally."""
        count = len(self._close_history)

        # Fast EMA
        if count >= self.ema_fast_period:
            if self._ema_fast is None:
                # First calculation: use SMA as seed
                self._ema_fast = sum(list(self._close_history)[-self.ema_fast_period:]) / self.ema_fast_period
            else:
                self._ema_fast = self._ema_fast + self._fast_factor * (close - self._ema_fast)

        # Slow EMA
        if count >= self.ema_slow_period:
            if self._ema_slow is None:
                self._ema_slow = sum(list(self._close_history)[-self.ema_slow_period:]) / self.ema_slow_period
            else:
                self._ema_slow = self._ema_slow + self._slow_factor * (close - self._ema_slow)

    def _detect_crossover(self):
        """Detect golden cross and dead cross from EMA values."""
        self._golden_cross = False
        self._dead_cross = False

        if (self._ema_fast is None or self._ema_slow is None or
                self._prev_ema_fast is None or self._prev_ema_slow is None):
            return

        prev_diff = self._prev_ema_fast - self._prev_ema_slow
        curr_diff = self._ema_fast - self._ema_slow

        # Golden cross: fast was below (or equal) slow, now above
        if prev_diff <= 0 and curr_diff > 0:
            self._golden_cross = True

        # Dead cross: fast was above (or equal) slow, now below
        if prev_diff >= 0 and curr_diff < 0:
            self._dead_cross = True

    def _on_candle(self, data: Dict[str, Any]):
        """Update EMAs on every candle (called before any trigger logic)."""
        close = data['close']
        self._prev_ema_fast = self._ema_fast
        self._prev_ema_slow = self._ema_slow
        self._close_history.append(close)
        self._update_emas(close)
        self._detect_crossover()

        # Re-arm trigger after crossover (so next opposite cross can fire)
        if not self._trigger_armed:
            if self._dead_cross or self._golden_cross:
                self._trigger_armed = True
                cross_type = "dead cross" if self._dead_cross else "golden cross"
                self.context.log(
                    f"[{self._log_prefix}] Trigger RE-ARMED ({cross_type}). "
                    f"EMA fast={self._ema_fast:.4f}, slow={self._ema_slow:.4f}"
                )

    def _check_entry_trigger(self, data: Dict[str, Any]) -> Optional[str]:
        """L1: Golden cross → long, Dead cross → short (when position_side='both')."""
        if not self._trigger_armed:
            return None

        if self._golden_cross:
            self._trigger_armed = False
            self.context.log(
                f"[{self._log_prefix}] GOLDEN CROSS! EMA fast({self.ema_fast_period})={self._ema_fast:.4f} > "
                f"slow({self.ema_slow_period})={self._ema_slow:.4f}"
            )
            return Side.LONG

        if self._dead_cross:
            self._trigger_armed = False
            self.context.log(
                f"[{self._log_prefix}] DEAD CROSS (SHORT)! EMA fast({self.ema_fast_period})={self._ema_fast:.4f} < "
                f"slow({self.ema_slow_period})={self._ema_slow:.4f}"
            )
            return Side.SHORT

        return None

    def _check_additional_trigger(self, data: Dict[str, Any]) -> bool:
        """L2+ (trigger mode): Golden cross re-occurrence after dead cross reset."""
        if not self._golden_cross:
            return False
        if not self._trigger_armed:
            return False

        self._trigger_armed = False
        self.context.log(
            f"[{self._log_prefix}] Additional GOLDEN CROSS! "
            f"EMA fast={self._ema_fast:.4f} > slow={self._ema_slow:.4f}"
        )
        return True

    def _check_exit_trigger(self, data: Dict[str, Any]) -> bool:
        """Exit on opposite cross: LONG exits on dead cross, SHORT exits on golden cross."""
        if self.is_short:
            # SHORT position: exit on golden cross (trend reversal upward)
            if not self._golden_cross:
                return False
            self.context.log(
                f"[{self._log_prefix}] GOLDEN CROSS → Cover SHORT! EMA fast({self.ema_fast_period})={self._ema_fast:.4f} > "
                f"slow({self.ema_slow_period})={self._ema_slow:.4f}"
            )
            return True
        else:
            # LONG position: exit on dead cross
            if not self._dead_cross:
                return False
            self.context.log(
                f"[{self._log_prefix}] DEAD CROSS → Sell LONG! EMA fast({self.ema_fast_period})={self._ema_fast:.4f} < "
                f"slow({self.ema_slow_period})={self._ema_slow:.4f}"
            )
            return True

    @property
    def _log_prefix(self) -> str:
        return "EmaMomentum"

    @property
    def _strategy_id(self) -> str:
        return "ema_momentum"

    def get_state(self) -> Dict[str, Any]:
        state = super().get_state()
        state["ema_fast"] = round(self._ema_fast, 4) if self._ema_fast is not None else None
        state["ema_slow"] = round(self._ema_slow, 4) if self._ema_slow is not None else None
        state["ema_fast_period"] = self.ema_fast_period
        state["ema_slow_period"] = self.ema_slow_period
        state["golden_cross"] = self._golden_cross
        state["dead_cross"] = self._dead_cross
        state["trigger_armed"] = self._trigger_armed
        return state
