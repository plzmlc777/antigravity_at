"""
Chart Pattern Strategy
- Detects chart patterns: Bottom (Double Bottom, V-Bottom), Top (Double Top), Convergence (Triangle)
- Entry trigger when selected pattern is detected
- All pattern detection uses configurable lookback periods and thresholds
"""

from typing import Dict, Any, List, Optional
from collections import deque
from .base import BaseStrategy, Side, customize_fields
from .martingale_base import MartingaleBase


class ChartPatternStrategy(MartingaleBase):
    """
    Chart Pattern Detection Strategy

    Supported patterns:
    - double_bottom: Two similar lows with a peak between (bullish reversal)
    - v_bottom: Sharp decline followed by sharp recovery (bullish reversal)
    - double_top: Two similar highs with a trough between (bearish - used for exit or skip)
    - triangle: Converging highs and lows (breakout expected)
    - wedge: Narrowing price channel (breakout expected)
    """

    PARAMETER_SCHEMA = {
        "fields": [
            {
                "name": "entry_patterns",
                "type": "multiselect",
                "label": "Entry Patterns (진입)",
                "default": "double_bottom",
                "options": [
                    {"value": "double_bottom", "label": "Double Bottom (W)"},
                    {"value": "v_bottom", "label": "V-Bottom"},
                    {"value": "triangle", "label": "Triangle (수렴)"},
                    {"value": "wedge", "label": "Wedge (쐐기)"},
                ],
                "description": "복수 선택 가능 (OR 로직 - 하나라도 감지되면 진입)",
                "show_in_table": True,
            },
            {
                "name": "exit_patterns",
                "type": "multiselect",
                "label": "Exit Patterns (매도)",
                "default": "",
                "options": [
                    {"value": "double_top", "label": "Double Top (M)"},
                    {"value": "v_top", "label": "V-Top"},
                    {"value": "triangle", "label": "Triangle (수렴)"},
                    {"value": "wedge", "label": "Wedge (쐐기)"},
                ],
                "description": "복수 선택 가능 (OR 로직 - 선택 안하면 트레일링 스탑만 사용)",
                "show_in_table": True,
            },
            {
                "name": "lookback_candles",
                "type": "number",
                "label": "Lookback Candles",
                "default": 20, "min": 10, "max": 100, "step": 5,
                "description": "Number of candles to analyze for pattern detection",
                "show_in_table": True, "defaultOptRange": "15, 20, 30, 50",
            },
            {
                "name": "tolerance_percent",
                "type": "number",
                "label": "Tolerance (%)",
                "default": 1.5, "min": 0.5, "max": 5.0, "step": 0.1,
                "description": "Price similarity tolerance for pattern matching",
                "show_in_table": True, "defaultOptRange": "1.0, 1.5, 2.0, 3.0",
            },
            {
                "name": "min_pattern_depth",
                "type": "number",
                "label": "Min Pattern Depth (%)",
                "default": 3.0, "min": 1.0, "max": 20.0, "step": 0.5,
                "description": "Minimum price swing % required for valid pattern",
                "show_in_table": True, "defaultOptRange": "2.0, 3.0, 5.0, 7.0",
            },
            {
                "name": "breakout_confirm",
                "type": "select",
                "label": "Breakout Confirmation",
                "default": "immediate",
                "options": ["immediate", "close_above", "volume_confirm"],
                "description": "How to confirm pattern completion before entry",
                "show_in_table": True,
            },
            {
                "name": "cooldown_candles",
                "type": "number",
                "label": "Cooldown Candles",
                "default": 5, "min": 0, "max": 50, "step": 1,
                "description": "Minimum candles between pattern signals",
                "show_in_table": False, "defaultOptRange": "3, 5, 10",
            },
        ] + customize_fields(BaseStrategy.COMMON_PARAMETER_FIELDS, {
            "max_buy_count": {"default": 3},
            "trailing_start_percent": {"default": 5.0},
            "trailing_stop_percent": {"default": 2.0},
        })
    }

    def _initialize_trigger(self):
        entry_patterns_raw = self.config.get("entry_patterns", "double_bottom")
        exit_patterns_raw = self.config.get("exit_patterns", "")

        if isinstance(entry_patterns_raw, str):
            self.entry_patterns = [p.strip() for p in entry_patterns_raw.split(",") if p.strip()]
        elif isinstance(entry_patterns_raw, list):
            self.entry_patterns = [p for p in entry_patterns_raw if p]
        else:
            self.entry_patterns = ["double_bottom"]

        if not self.entry_patterns:
            self.entry_patterns = ["double_bottom"]

        if isinstance(exit_patterns_raw, str):
            self.exit_patterns = [p.strip() for p in exit_patterns_raw.split(",") if p.strip()]
        elif isinstance(exit_patterns_raw, list):
            self.exit_patterns = [p for p in exit_patterns_raw if p]
        else:
            self.exit_patterns = []

        self.lookback = int(self.config.get("lookback_candles", 20))
        self.tolerance = float(self.config.get("tolerance_percent", 1.5)) / 100.0
        self.min_depth = float(self.config.get("min_pattern_depth", 3.0)) / 100.0
        self.breakout_confirm = self.config.get("breakout_confirm", "immediate")
        self.cooldown = int(self.config.get("cooldown_candles", 5))

        self._candle_history: deque = deque(maxlen=self.lookback + 10)
        self._last_entry_pattern: Optional[str] = None
        self._last_entry_pattern_price: float = 0.0
        self._candles_since_entry_signal: int = 999
        self._entry_pattern_detected: bool = False
        self._entry_trigger_armed: bool = True
        self._last_exit_pattern: Optional[str] = None
        self._last_exit_pattern_price: float = 0.0
        self._exit_pattern_detected: bool = False

    def preload_history(self, candles: list):
        needed = self.lookback + 5
        recent = candles[-needed:] if len(candles) >= needed else candles
        for candle in recent:
            self._candle_history.append({
                'open': candle.get('open', 0),
                'high': candle.get('high', 0),
                'low': candle.get('low', 0),
                'close': candle.get('close', 0),
                'volume': candle.get('volume', 0),
            })

    def _on_candle(self, data: Dict[str, Any]):
        self._candle_history.append({
            'open': data.get('open', data['close']),
            'high': data.get('high', data['close']),
            'low': data.get('low', data['close']),
            'close': data['close'],
            'volume': data.get('volume', 0),
        })
        self._candles_since_entry_signal += 1

        if not self._entry_trigger_armed and self._candles_since_entry_signal >= self.cooldown:
            self._entry_trigger_armed = True

    def _check_entry_trigger(self, data: Dict[str, Any]) -> Optional[str]:
        if not self._entry_trigger_armed:
            return None
        if len(self._candle_history) < self.lookback:
            return None

        candles = list(self._candle_history)[-self.lookback:]
        detected_pattern = self._detect_entry_pattern(candles, data['close'])

        if detected_pattern:
            self._last_entry_pattern = detected_pattern
            self._last_entry_pattern_price = data['close']
            self._candles_since_entry_signal = 0
            self._entry_trigger_armed = False
            self._entry_pattern_detected = True
            return Side.LONG
        return None

    def _check_additional_trigger(self, data: Dict[str, Any]) -> bool:
        return self._check_entry_trigger(data)

    def _check_exit_trigger(self, data: Dict[str, Any]) -> bool:
        if not self.exit_patterns:
            return False
        if len(self._candle_history) < self.lookback:
            return False

        candles = list(self._candle_history)[-self.lookback:]
        detected_pattern = self._detect_exit_pattern(candles, data['close'])

        if detected_pattern:
            self._last_exit_pattern = detected_pattern
            self._last_exit_pattern_price = data['close']
            self._exit_pattern_detected = True
            return True
        return False

    def _detect_entry_pattern(self, candles: List[dict], current_price: float) -> Optional[str]:
        pattern_detectors = {
            "double_bottom": lambda: self._detect_double_bottom(candles, current_price),
            "v_bottom": lambda: self._detect_v_bottom(candles, current_price),
            "triangle": lambda: self._detect_triangle(candles, current_price, direction="up"),
            "wedge": lambda: self._detect_wedge(candles, current_price, direction="up"),
        }
        for pattern_type in self.entry_patterns:
            if pattern_type in pattern_detectors:
                result = pattern_detectors[pattern_type]()
                if result:
                    return result
        return None

    def _detect_exit_pattern(self, candles: List[dict], current_price: float) -> Optional[str]:
        if not self.exit_patterns:
            return None
        pattern_detectors = {
            "double_top": lambda: self._detect_double_top(candles, current_price),
            "v_top": lambda: self._detect_v_top(candles, current_price),
            "triangle": lambda: self._detect_triangle(candles, current_price, direction="down"),
            "wedge": lambda: self._detect_wedge(candles, current_price, direction="down"),
        }
        for pattern_type in self.exit_patterns:
            if pattern_type in pattern_detectors:
                result = pattern_detectors[pattern_type]()
                if result:
                    return result
        return None

    def _detect_double_bottom(self, candles: List[dict], current_price: float) -> Optional[str]:
        lows = [c['low'] for c in candles]
        highs = [c['high'] for c in candles]
        min_idx1 = lows.index(min(lows))
        second_lows = [(i, lows[i]) for i in range(len(lows)) if abs(i - min_idx1) >= 3]
        if not second_lows:
            return None
        min_idx2, min_val2 = min(second_lows, key=lambda x: x[1])
        min_val1 = lows[min_idx1]
        avg_low = (min_val1 + min_val2) / 2
        if abs(min_val1 - min_val2) / avg_low > self.tolerance:
            return None
        left_idx, right_idx = min(min_idx1, min_idx2), max(min_idx1, min_idx2)
        if right_idx - left_idx < 3:
            return None
        middle_highs = highs[left_idx:right_idx+1]
        neckline = max(middle_highs)
        depth = (neckline - avg_low) / neckline
        if depth < self.min_depth:
            return None
        if self.breakout_confirm == "immediate":
            if current_price > neckline:
                return "double_bottom"
        elif self.breakout_confirm == "close_above":
            if candles[-1]['close'] > neckline:
                return "double_bottom"
        elif self.breakout_confirm == "volume_confirm":
            avg_vol = sum(c['volume'] for c in candles[:-1]) / (len(candles) - 1)
            if current_price > neckline and candles[-1]['volume'] > avg_vol * 1.2:
                return "double_bottom"
        return None

    def _detect_v_bottom(self, candles: List[dict], current_price: float) -> Optional[str]:
        closes = [c['close'] for c in candles]
        lows = [c['low'] for c in candles]
        min_idx = lows.index(min(lows))
        min_price = lows[min_idx]
        if min_idx < 3 or min_idx > len(candles) - 3:
            return None
        pre_high = max(c['high'] for c in candles[:min_idx])
        decline = (pre_high - min_price) / pre_high
        post_high = max(c['high'] for c in candles[min_idx:])
        recovery = (post_high - min_price) / min_price
        if decline < self.min_depth or recovery < self.min_depth * 0.7:
            return None
        if recovery < decline * 0.6:
            return None
        if current_price > closes[min_idx] * (1 + self.min_depth * 0.5):
            return "v_bottom"
        return None

    def _detect_double_top(self, candles: List[dict], current_price: float) -> Optional[str]:
        highs = [c['high'] for c in candles]
        lows = [c['low'] for c in candles]
        max_idx1 = highs.index(max(highs))
        second_highs = [(i, highs[i]) for i in range(len(highs)) if abs(i - max_idx1) >= 3]
        if not second_highs:
            return None
        max_idx2, max_val2 = max(second_highs, key=lambda x: x[1])
        max_val1 = highs[max_idx1]
        avg_high = (max_val1 + max_val2) / 2
        if abs(max_val1 - max_val2) / avg_high > self.tolerance:
            return None
        left_idx, right_idx = min(max_idx1, max_idx2), max(max_idx1, max_idx2)
        if right_idx - left_idx < 3:
            return None
        middle_lows = lows[left_idx:right_idx+1]
        neckline = min(middle_lows)
        depth = (avg_high - neckline) / avg_high
        if depth < self.min_depth:
            return None
        if self.breakout_confirm == "immediate":
            if current_price < neckline:
                return "double_top"
        elif self.breakout_confirm == "close_above":
            if candles[-1]['close'] < neckline:
                return "double_top"
        elif self.breakout_confirm == "volume_confirm":
            avg_vol = sum(c['volume'] for c in candles[:-1]) / (len(candles) - 1)
            if current_price < neckline and candles[-1]['volume'] > avg_vol * 1.2:
                return "double_top"
        return None

    def _detect_v_top(self, candles: List[dict], current_price: float) -> Optional[str]:
        closes = [c['close'] for c in candles]
        highs = [c['high'] for c in candles]
        max_idx = highs.index(max(highs))
        max_price = highs[max_idx]
        if max_idx < 3 or max_idx > len(candles) - 3:
            return None
        pre_low = min(c['low'] for c in candles[:max_idx])
        rise = (max_price - pre_low) / pre_low
        post_low = min(c['low'] for c in candles[max_idx:])
        decline = (max_price - post_low) / max_price
        if rise < self.min_depth or decline < self.min_depth * 0.7:
            return None
        if decline < rise * 0.6:
            return None
        if current_price < closes[max_idx] * (1 - self.min_depth * 0.5):
            return "v_top"
        return None

    def _detect_triangle(self, candles: List[dict], current_price: float, direction: str = "up") -> Optional[str]:
        highs = [c['high'] for c in candles]
        lows = [c['low'] for c in candles]
        half = len(candles) // 2
        first_half_range = max(highs[:half]) - min(lows[:half])
        second_half_range = max(highs[half:]) - min(lows[half:])
        if second_half_range >= first_half_range * 0.9:
            return None
        high_trend = (highs[-1] - highs[0]) / highs[0]
        low_trend = (lows[-1] - lows[0]) / lows[0]
        avg_price = sum(c['close'] for c in candles) / len(candles)
        convergence = first_half_range - second_half_range
        if convergence / avg_price < self.min_depth * 0.3:
            return None
        recent_high = max(highs[-3:])
        recent_low = min(lows[-3:])
        if direction == "up":
            if current_price > recent_high and high_trend <= 0:
                return "triangle_up"
        else:
            if current_price < recent_low and low_trend >= 0:
                return "triangle_down"
        return None

    def _detect_wedge(self, candles: List[dict], current_price: float, direction: str = "up") -> Optional[str]:
        highs = [c['high'] for c in candles]
        lows = [c['low'] for c in candles]
        n = len(candles)
        x_sum = sum(range(n))
        x2_sum = sum(i*i for i in range(n))
        high_xy = sum(i * highs[i] for i in range(n))
        low_xy = sum(i * lows[i] for i in range(n))
        high_y = sum(highs)
        low_y = sum(lows)
        denom = n * x2_sum - x_sum * x_sum
        if denom == 0:
            return None
        high_slope = (n * high_xy - x_sum * high_y) / denom
        low_slope = (n * low_xy - x_sum * low_y) / denom
        avg_price = (high_y + low_y) / (2 * n)
        high_slope_pct = high_slope / avg_price
        low_slope_pct = low_slope / avg_price
        if direction == "up":
            if high_slope < 0 and low_slope < 0:
                if low_slope_pct < high_slope_pct:
                    if current_price > max(highs[-3:]):
                        return "falling_wedge"
        else:
            if high_slope > 0 and low_slope > 0:
                if high_slope_pct < low_slope_pct:
                    if current_price < min(lows[-3:]):
                        return "rising_wedge"
        return None

    @property
    def _log_prefix(self) -> str:
        return "ChartPattern"

    @property
    def _strategy_id(self) -> str:
        return "chart_pattern"

    def get_state(self) -> Dict[str, Any]:
        state = super().get_state()
        pattern_labels = {
            "double_bottom": "Double Bottom (W)",
            "v_bottom": "V-Bottom",
            "double_top": "Double Top (M)",
            "v_top": "V-Top",
            "triangle": "Triangle",
            "triangle_up": "Triangle ↑",
            "triangle_down": "Triangle ↓",
            "wedge": "Wedge",
            "falling_wedge": "Falling Wedge ↑",
            "rising_wedge": "Rising Wedge ↓",
        }
        state["entry_patterns"] = self.entry_patterns
        state["entry_patterns_labels"] = [pattern_labels.get(p, p) for p in self.entry_patterns]
        state["last_entry_pattern"] = self._last_entry_pattern
        state["last_entry_pattern_price"] = self._last_entry_pattern_price
        state["entry_pattern_detected"] = self._entry_pattern_detected
        state["entry_trigger_armed"] = self._entry_trigger_armed
        state["candles_since_entry_signal"] = self._candles_since_entry_signal
        state["exit_patterns"] = self.exit_patterns
        state["exit_patterns_labels"] = [pattern_labels.get(p, p) for p in self.exit_patterns] if self.exit_patterns else []
        state["last_exit_pattern"] = self._last_exit_pattern
        state["last_exit_pattern_price"] = self._last_exit_pattern_price
        state["exit_pattern_detected"] = self._exit_pattern_detected
        state["cooldown"] = self.cooldown
        state["lookback"] = self.lookback
        state["history_size"] = len(self._candle_history)
        if self._last_entry_pattern:
            state["entry_pattern_label"] = pattern_labels.get(self._last_entry_pattern, self._last_entry_pattern)
        if self._last_exit_pattern:
            state["exit_pattern_label"] = pattern_labels.get(self._last_exit_pattern, self._last_exit_pattern)
        return state
