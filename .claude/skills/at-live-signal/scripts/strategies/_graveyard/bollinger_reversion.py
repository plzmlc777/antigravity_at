from typing import Dict, Any, Optional
from collections import deque
import math

from .base import BaseStrategy, customize_fields
from .martingale_base import MartingaleBase
from app.core.constants import Side


class BollingerReversionStrategy(MartingaleBase):
    """
    Bollinger Band Mean-Reversion Strategy.

    - Entry trigger: Price touches a Bollinger Band.
        * lower band touch -> LONG (buy the dip, expect reversion to mean)
        * upper band touch -> SHORT (sell the rip, expect reversion to mean)
    - entry_band parameter controls which touches are traded: lower / upper / both.
    - Single entry only (_check_additional_trigger returns False). Martingale default off.
    - SMA and stddev are computed incrementally from a rolling deque of closes
      sized to bb_period.

    Gap signal: GAP-20260408-004 (meta-learner) — fills missing mean-reversion
    entry trigger in strategy pool. Paper-mode only on creation; promotion to
    live gated by risk-manager KPI (>=12%/month compound).
    """

    PARAMETER_SCHEMA = {
        "fields": [
            {"name": "bb_period", "type": "number", "label": "BB Period",
             "default": 20, "min": 5, "max": 200, "step": 1,
             "description": "Number of candles for SMA and stddev calculation",
             "show_in_table": True, "defaultOptRange": "10, 20, 30, 50"},
            {"name": "bb_std_dev", "type": "number", "label": "BB StdDev Multiplier",
             "default": 2.0, "min": 0.5, "max": 5.0, "step": 0.1,
             "description": "Standard deviation multiplier for band width",
             "show_in_table": True, "defaultOptRange": "1.5, 2.0, 2.5, 3.0"},
            {"name": "entry_band", "type": "select", "label": "Entry Band",
             "default": "both", "options": ["lower", "upper", "both"],
             "description": "lower=long on lower touch, upper=short on upper touch, both=trade either side",
             "show_in_table": True},
        ] + customize_fields(BaseStrategy.COMMON_PARAMETER_FIELDS, {
            "max_buy_count": {"default": 1},
            "use_martingale": {"default": "off"},
            "trailing_start_percent": {"default": 0},
            "trailing_stop_percent": {"default": 0},
        })
    }

    def _initialize_trigger(self):
        self.bb_period = int(self.config.get("bb_period", 20) or 20)
        if self.bb_period < 2:
            self.bb_period = 2
        self.bb_std_dev = float(self.config.get("bb_std_dev", 2.0) or 2.0)
        self.entry_band = (self.config.get("entry_band", "both") or "both").lower()
        if self.entry_band not in ("lower", "upper", "both"):
            self.entry_band = "both"

        self._close_history: deque = deque(maxlen=self.bb_period)
        self._sma: float = 0.0
        self._stddev: float = 0.0
        self._upper: float = 0.0
        self._lower: float = 0.0
        self._bands_ready: bool = False

    def _recompute_bands(self):
        """Incremental-ish recompute over the rolling window (O(period)).

        The window is bounded by bb_period so this is constant-time per candle
        and avoids floating-point drift that a pure running-sum update would
        accumulate over long sessions.
        """
        n = len(self._close_history)
        if n < self.bb_period:
            self._bands_ready = False
            return
        s = 0.0
        for c in self._close_history:
            s += c
        mean = s / n
        var_sum = 0.0
        for c in self._close_history:
            d = c - mean
            var_sum += d * d
        variance = var_sum / n
        stddev = math.sqrt(variance) if variance > 0 else 0.0
        self._sma = mean
        self._stddev = stddev
        self._upper = mean + self.bb_std_dev * stddev
        self._lower = mean - self.bb_std_dev * stddev
        self._bands_ready = True

    def preload_history(self, candles: list):
        """Warm the rolling window from historical candles so bands are ready
        on the first live candle."""
        if not candles:
            return
        needed = self.bb_period
        recent = candles[-needed:] if len(candles) >= needed else candles
        for candle in recent:
            close = candle.get('close', 0)
            if close and close > 0:
                self._close_history.append(float(close))
        self._recompute_bands()

    def _on_candle(self, data: Dict[str, Any]):
        """Update rolling window + recompute bands every candle, before trigger checks."""
        close = data.get('close', 0)
        if close and close > 0:
            self._close_history.append(float(close))
            self._recompute_bands()

    def _check_entry_trigger(self, data: Dict[str, Any]) -> Optional[str]:
        """Return Side.LONG on lower-band touch, Side.SHORT on upper-band touch.

        'Touch' = candle low <= lower band (long) or candle high >= upper band
        (short). Falls back to close if OHLC is missing.
        """
        if not self._bands_ready:
            return None
        close = data.get('close', 0)
        if not close or close <= 0:
            return None
        low = data.get('low', close)
        high = data.get('high', close)

        lower_touch = low <= self._lower
        upper_touch = high >= self._upper

        if self.entry_band in ("lower", "both") and lower_touch:
            return Side.LONG
        if self.entry_band in ("upper", "both") and upper_touch:
            return Side.SHORT
        return None

    def _check_additional_trigger(self, data: Dict[str, Any]) -> bool:
        # Single-entry mean reversion; martingale off by default.
        return False

    @property
    def _log_prefix(self) -> str:
        return "BollingerReversion"

    @property
    def _strategy_id(self) -> str:
        return "bollinger_reversion"

    def get_state(self) -> Dict[str, Any]:
        state = super().get_state()
        state["bb_period"] = self.bb_period
        state["bb_std_dev"] = self.bb_std_dev
        state["entry_band"] = self.entry_band
        state["bb_sma"] = round(self._sma, 6) if self._bands_ready else None
        state["bb_upper"] = round(self._upper, 6) if self._bands_ready else None
        state["bb_lower"] = round(self._lower, 6) if self._bands_ready else None
        state["bb_stddev"] = round(self._stddev, 6) if self._bands_ready else None
        state["bands_ready"] = self._bands_ready
        return state
