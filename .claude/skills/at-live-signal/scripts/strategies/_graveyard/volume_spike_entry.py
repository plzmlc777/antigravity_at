from typing import Dict, Any, Optional
from collections import deque
from .base import BaseStrategy, customize_fields
from .martingale_base import MartingaleBase
from app.core.constants import Side


class VolumeSpikeEntryStrategy(MartingaleBase):
    """
    Volume Spike Entry Strategy (SAS audition — category: volume)

    - Entry trigger: Current candle volume >= (volume_multiple * average volume over lookback bars).
      If triggered, bullish candle (close > open) -> long, bearish (close < open) -> short.
    - Direction filter: long / short / both (configurable).
    - Single entry by default (max_buy_count=1, martingale off, trailing stop off).

    Provenance: GAP-20260408-005 (CIO-20260408-015 Phase 1 verification).
    """

    PARAMETER_SCHEMA = {
        "fields": [
            {"name": "volume_multiple", "type": "number", "label": "Volume Multiple (x)",
             "default": 2.5, "min": 1.0, "max": 20.0, "step": 0.1,
             "description": "Required multiple of average volume over lookback bars to trigger entry",
             "show_in_table": True, "defaultOptRange": "1.5, 2.0, 2.5, 3.0, 4.0"},
            {"name": "lookback", "type": "number", "label": "Lookback Bars",
             "default": 20, "min": 5, "max": 200, "step": 1,
             "description": "Number of candles used to compute the rolling average volume baseline",
             "show_in_table": True, "defaultOptRange": "10, 20, 30, 50"},
            {"name": "direction", "type": "select", "label": "Direction",
             "default": "both", "options": ["long", "short", "both"],
             "description": "long = only buy bullish spikes; short = only sell bearish spikes; both = allow either",
             "show_in_table": True},
        ] + customize_fields(BaseStrategy.COMMON_PARAMETER_FIELDS, {
            "max_buy_count": {"default": 1},
            "use_martingale": {"default": "off"},
            "trailing_start_percent": {"default": 0},
            "trailing_stop_percent": {"default": 0},
        })
    }

    def _initialize_trigger(self):
        self.volume_multiple = float(self.config.get("volume_multiple", 2.5) or 2.5)
        self.lookback = int(self.config.get("lookback", 20) or 20)
        self.direction = self.config.get("direction", "both") or "both"
        self._volume_history: deque = deque(maxlen=self.lookback)
        self._avg_volume = 0.0
        self._last_ratio = 0.0

    def preload_history(self, candles: list):
        """Preload recent candle volumes so the average is ready immediately."""
        recent = candles[-self.lookback:] if len(candles) >= self.lookback else candles
        for candle in recent:
            vol = candle.get('volume', 0) or 0
            if vol > 0:
                self._volume_history.append(float(vol))
        if self._volume_history:
            self._avg_volume = sum(self._volume_history) / len(self._volume_history)

    def _on_candle(self, data: Dict[str, Any]):
        """Update rolling volume baseline every candle (before entry check)."""
        vol = float(data.get('volume', 0) or 0)
        if vol <= 0:
            return
        # Compute ratio against the PREVIOUS baseline (exclude current bar)
        if self._volume_history:
            prev_avg = sum(self._volume_history) / len(self._volume_history)
            self._avg_volume = prev_avg
            self._last_ratio = vol / prev_avg if prev_avg > 0 else 0.0
        else:
            self._avg_volume = 0.0
            self._last_ratio = 0.0
        # Append current bar to the rolling window for next tick
        self._volume_history.append(vol)

    def _check_entry_trigger(self, data: Dict[str, Any]) -> Optional[str]:
        """
        Trigger when current-bar volume >= volume_multiple * prior-avg volume.
        Direction is inferred from the candle body (bullish -> long, bearish -> short),
        filtered by the `direction` parameter.
        """
        # Need a full lookback window before firing
        if len(self._volume_history) < self.lookback:
            return None
        if self._avg_volume <= 0:
            return None
        if self._last_ratio < self.volume_multiple:
            return None

        candle_open = float(data.get('open', 0) or 0)
        candle_close = float(data.get('close', 0) or 0)
        if candle_open <= 0 or candle_close <= 0:
            return None

        if candle_close > candle_open:
            desired = Side.LONG
        elif candle_close < candle_open:
            desired = Side.SHORT
        else:
            return None  # doji — no directional conviction

        if self.direction == "long" and desired != Side.LONG:
            return None
        if self.direction == "short" and desired != Side.SHORT:
            return None
        return desired

    def _check_additional_trigger(self, data: Dict[str, Any]) -> bool:
        """Single-entry strategy by default; no L2+ pyramiding."""
        return False

    @property
    def _log_prefix(self) -> str:
        return "VolumeSpikeEntry"

    @property
    def _strategy_id(self) -> str:
        return "volume_spike_entry"

    def get_state(self) -> Dict[str, Any]:
        state = super().get_state()
        state["avg_volume"] = round(self._avg_volume, 2) if self._avg_volume else 0
        state["last_volume_ratio"] = round(self._last_ratio, 3)
        state["volume_multiple"] = self.volume_multiple
        state["lookback"] = self.lookback
        state["direction"] = self.direction
        return state
