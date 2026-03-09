"""
Chart Pattern Strategy
- Detects chart patterns: Bottom (Double Bottom, V-Bottom), Top (Double Top), Convergence (Triangle)
- Entry trigger when selected pattern is detected
- All pattern detection uses configurable lookback periods and thresholds
"""

from typing import Dict, Any, List, Optional
from collections import deque
from .base import BaseStrategy, customize_fields
from .martingale_base import MartingaleBase
from ..core.constants import Side


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
                "default": 20,
                "min": 10,
                "max": 100,
                "step": 5,
                "description": "Number of candles to analyze for pattern detection",
                "show_in_table": True,
                "defaultOptRange": "15, 20, 30, 50",
            },
            {
                "name": "tolerance_percent",
                "type": "number",
                "label": "Tolerance (%)",
                "default": 1.5,
                "min": 0.5,
                "max": 5.0,
                "step": 0.1,
                "description": "Price similarity tolerance for pattern matching (e.g., two bottoms within 1.5%)",
                "show_in_table": True,
                "defaultOptRange": "1.0, 1.5, 2.0, 3.0",
            },
            {
                "name": "min_pattern_depth",
                "type": "number",
                "label": "Min Pattern Depth (%)",
                "default": 3.0,
                "min": 1.0,
                "max": 20.0,
                "step": 0.5,
                "description": "Minimum price swing % required for valid pattern",
                "show_in_table": True,
                "defaultOptRange": "2.0, 3.0, 5.0, 7.0",
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
                "default": 5,
                "min": 0,
                "max": 50,
                "step": 1,
                "description": "Minimum candles between pattern signals (prevent over-trading)",
                "show_in_table": False,
                "defaultOptRange": "3, 5, 10",
            },
        ] + customize_fields(BaseStrategy.COMMON_PARAMETER_FIELDS, {
            "max_buy_count": {"default": 3},
            "trailing_start_percent": {"default": 5.0},
            "trailing_stop_percent": {"default": 2.0},
        })
    }

    def _initialize_trigger(self):
        """Initialize pattern detection parameters."""
        # Handle multiselect format: comma-separated string (e.g., "double_bottom,v_bottom")
        entry_patterns_raw = self.config.get("entry_patterns", "double_bottom")
        exit_patterns_raw = self.config.get("exit_patterns", "")

        # Parse multiselect values (comma-separated string → list)
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

        # Price history for pattern analysis
        self._candle_history: deque = deque(maxlen=self.lookback + 10)

        # Pattern detection state (entry)
        self._last_entry_pattern: Optional[str] = None
        self._last_entry_pattern_price: float = 0.0
        self._candles_since_entry_signal: int = 999
        self._entry_pattern_detected: bool = False
        self._entry_trigger_armed: bool = True

        # Pattern detection state (exit)
        self._last_exit_pattern: Optional[str] = None
        self._last_exit_pattern_price: float = 0.0
        self._exit_pattern_detected: bool = False

    def preload_history(self, candles: list):
        """Preload candle history for immediate pattern detection."""
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
        """Update candle history and check patterns."""
        self._candle_history.append({
            'open': data.get('open', data['close']),
            'high': data.get('high', data['close']),
            'low': data.get('low', data['close']),
            'close': data['close'],
            'volume': data.get('volume', 0),
        })
        self._candles_since_entry_signal += 1

        # Re-arm entry trigger after cooldown
        if not self._entry_trigger_armed and self._candles_since_entry_signal >= self.cooldown:
            self._entry_trigger_armed = True

    def _check_entry_trigger(self, data: Dict[str, Any]) -> Optional[str]:
        """Check if selected entry pattern is detected."""
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
        """Additional entries on continued pattern confirmation."""
        # Use same pattern logic for additional entries
        return self._check_entry_trigger(data)

    def _check_exit_trigger(self, data: Dict[str, Any]) -> bool:
        """Check if any exit pattern is detected for selling position."""
        # If no exit patterns selected, rely on trailing stop / stop loss (handled by MartingaleBase)
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
        """
        Detect entry (buy) pattern based on configuration.
        Uses OR logic - returns first detected pattern from selected list.
        Returns pattern name if detected, None otherwise.
        """
        # Pattern detection mapping
        pattern_detectors = {
            "double_bottom": lambda: self._detect_double_bottom(candles, current_price),
            "v_bottom": lambda: self._detect_v_bottom(candles, current_price),
            "triangle": lambda: self._detect_triangle(candles, current_price, direction="up"),
            "wedge": lambda: self._detect_wedge(candles, current_price, direction="up"),
        }

        # Check each selected pattern (OR logic)
        for pattern_type in self.entry_patterns:
            if pattern_type in pattern_detectors:
                result = pattern_detectors[pattern_type]()
                if result:
                    return result

        return None

    def _detect_exit_pattern(self, candles: List[dict], current_price: float) -> Optional[str]:
        """
        Detect exit (sell) pattern based on configuration.
        Uses OR logic - returns first detected pattern from selected list.
        Returns pattern name if detected, None otherwise.
        """
        if not self.exit_patterns:
            return None

        # Pattern detection mapping
        pattern_detectors = {
            "double_top": lambda: self._detect_double_top(candles, current_price),
            "v_top": lambda: self._detect_v_top(candles, current_price),
            "triangle": lambda: self._detect_triangle(candles, current_price, direction="down"),
            "wedge": lambda: self._detect_wedge(candles, current_price, direction="down"),
        }

        # Check each selected pattern (OR logic)
        for pattern_type in self.exit_patterns:
            if pattern_type in pattern_detectors:
                result = pattern_detectors[pattern_type]()
                if result:
                    return result

        return None

    def _detect_double_bottom(self, candles: List[dict], current_price: float) -> Optional[str]:
        """
        Detect Double Bottom (W pattern):
        - Two similar lows with a peak between them
        - Current price breaks above the middle peak (neckline)
        """
        lows = [c['low'] for c in candles]
        highs = [c['high'] for c in candles]

        # Find two lowest points
        min_idx1 = lows.index(min(lows))

        # Find second lowest in different region (at least 3 candles apart)
        second_lows = [(i, lows[i]) for i in range(len(lows))
                       if abs(i - min_idx1) >= 3]
        if not second_lows:
            return None

        min_idx2, min_val2 = min(second_lows, key=lambda x: x[1])
        min_val1 = lows[min_idx1]

        # Check if two lows are similar (within tolerance)
        avg_low = (min_val1 + min_val2) / 2
        if abs(min_val1 - min_val2) / avg_low > self.tolerance:
            return None

        # Find peak between the two lows
        left_idx, right_idx = min(min_idx1, min_idx2), max(min_idx1, min_idx2)
        if right_idx - left_idx < 3:
            return None

        middle_highs = highs[left_idx:right_idx+1]
        neckline = max(middle_highs)

        # Check minimum depth
        depth = (neckline - avg_low) / neckline
        if depth < self.min_depth:
            return None

        # Check breakout confirmation
        if self.breakout_confirm == "immediate":
            if current_price > neckline:
                return "double_bottom"
        elif self.breakout_confirm == "close_above":
            if candles[-1]['close'] > neckline:
                return "double_bottom"
        elif self.breakout_confirm == "volume_confirm":
            # Volume should be higher on breakout
            avg_vol = sum(c['volume'] for c in candles[:-1]) / (len(candles) - 1)
            if current_price > neckline and candles[-1]['volume'] > avg_vol * 1.2:
                return "double_bottom"

        return None

    def _detect_v_bottom(self, candles: List[dict], current_price: float) -> Optional[str]:
        """
        Detect V-Bottom:
        - Sharp decline followed by sharp recovery
        - Forms a V shape
        """
        closes = [c['close'] for c in candles]
        lows = [c['low'] for c in candles]

        # Find the lowest point
        min_idx = lows.index(min(lows))
        min_price = lows[min_idx]

        # Need some candles before and after the minimum
        if min_idx < 3 or min_idx > len(candles) - 3:
            return None

        # Check decline before minimum
        pre_high = max(c['high'] for c in candles[:min_idx])
        decline = (pre_high - min_price) / pre_high

        # Check recovery after minimum
        post_high = max(c['high'] for c in candles[min_idx:])
        recovery = (post_high - min_price) / min_price

        # Both decline and recovery should be significant
        if decline < self.min_depth or recovery < self.min_depth * 0.7:
            return None

        # V should be relatively symmetric (recovery at least 60% of decline)
        if recovery < decline * 0.6:
            return None

        # Current price should be recovering
        if current_price > closes[min_idx] * (1 + self.min_depth * 0.5):
            return "v_bottom"

        return None

    def _detect_double_top(self, candles: List[dict], current_price: float) -> Optional[str]:
        """
        Detect Double Top (M pattern) - bearish reversal for exit:
        - Two similar highs with a trough between them
        - Current price breaks below the middle trough (neckline)
        """
        highs = [c['high'] for c in candles]
        lows = [c['low'] for c in candles]

        # Find two highest points
        max_idx1 = highs.index(max(highs))

        # Find second highest in different region (at least 3 candles apart)
        second_highs = [(i, highs[i]) for i in range(len(highs))
                        if abs(i - max_idx1) >= 3]
        if not second_highs:
            return None

        max_idx2, max_val2 = max(second_highs, key=lambda x: x[1])
        max_val1 = highs[max_idx1]

        # Check if two highs are similar (within tolerance)
        avg_high = (max_val1 + max_val2) / 2
        if abs(max_val1 - max_val2) / avg_high > self.tolerance:
            return None

        # Find trough between the two highs
        left_idx, right_idx = min(max_idx1, max_idx2), max(max_idx1, max_idx2)
        if right_idx - left_idx < 3:
            return None

        middle_lows = lows[left_idx:right_idx+1]
        neckline = min(middle_lows)

        # Check minimum depth
        depth = (avg_high - neckline) / avg_high
        if depth < self.min_depth:
            return None

        # Check breakdown confirmation
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
        """
        Detect V-Top (inverted V) - bearish reversal for exit:
        - Sharp rise followed by sharp decline
        - Forms an inverted V shape
        """
        closes = [c['close'] for c in candles]
        highs = [c['high'] for c in candles]

        # Find the highest point
        max_idx = highs.index(max(highs))
        max_price = highs[max_idx]

        # Need some candles before and after the maximum
        if max_idx < 3 or max_idx > len(candles) - 3:
            return None

        # Check rise before maximum
        pre_low = min(c['low'] for c in candles[:max_idx])
        rise = (max_price - pre_low) / pre_low

        # Check decline after maximum
        post_low = min(c['low'] for c in candles[max_idx:])
        decline = (max_price - post_low) / max_price

        # Both rise and decline should be significant
        if rise < self.min_depth or decline < self.min_depth * 0.7:
            return None

        # V-top should be relatively symmetric (decline at least 60% of rise)
        if decline < rise * 0.6:
            return None

        # Current price should be declining
        if current_price < closes[max_idx] * (1 - self.min_depth * 0.5):
            return "v_top"

        return None

    def _detect_triangle(self, candles: List[dict], current_price: float, direction: str = "up") -> Optional[str]:
        """
        Detect Triangle (Symmetrical/Ascending/Descending):
        - Converging trendlines of highs and lows
        - Decreasing volatility
        - direction="up" for entry (buy on upper breakout)
        - direction="down" for exit (sell on lower breakdown)
        """
        highs = [c['high'] for c in candles]
        lows = [c['low'] for c in candles]

        # Split into two halves
        half = len(candles) // 2
        first_half_range = max(highs[:half]) - min(lows[:half])
        second_half_range = max(highs[half:]) - min(lows[half:])

        # Range should be decreasing (convergence)
        if second_half_range >= first_half_range * 0.9:
            return None

        # Calculate trend of highs and lows
        high_trend = (highs[-1] - highs[0]) / highs[0]
        low_trend = (lows[-1] - lows[0]) / lows[0]

        # Check for convergence (opposite or converging trends)
        avg_price = sum(c['close'] for c in candles) / len(candles)
        convergence = first_half_range - second_half_range

        if convergence / avg_price < self.min_depth * 0.3:
            return None

        # Breakout detection
        recent_high = max(highs[-3:])
        recent_low = min(lows[-3:])

        if direction == "up":
            # Upper breakout for entry (buy signal)
            if current_price > recent_high and high_trend <= 0:
                return "triangle_up"
        else:
            # Lower breakdown for exit (sell signal)
            if current_price < recent_low and low_trend >= 0:
                return "triangle_down"

        return None

    def _detect_wedge(self, candles: List[dict], current_price: float, direction: str = "up") -> Optional[str]:
        """
        Detect Wedge pattern:
        - Falling wedge (bullish): Both highs and lows declining, but lows declining faster
        - Rising wedge (bearish): Both highs and lows rising, but highs rising slower
        - direction="up" for entry (buy on falling wedge breakout)
        - direction="down" for exit (sell on rising wedge breakdown)
        """
        highs = [c['high'] for c in candles]
        lows = [c['low'] for c in candles]

        # Simple linear regression approximation
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
            # For entry: look for falling wedge (bullish)
            if high_slope < 0 and low_slope < 0:
                # Lows should decline faster (more negative) for falling wedge
                if low_slope_pct < high_slope_pct:
                    # Check for upward breakout
                    if current_price > max(highs[-3:]):
                        return "falling_wedge"
        else:
            # For exit: look for rising wedge (bearish)
            if high_slope > 0 and low_slope > 0:
                # Highs should rise slower for rising wedge
                if high_slope_pct < low_slope_pct:
                    # Check for downward breakdown
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
        """Return current strategy state for UI display."""
        state = super().get_state()

        # Pattern labels mapping
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

        # Entry patterns info (list)
        state["entry_patterns"] = self.entry_patterns
        state["entry_patterns_labels"] = [pattern_labels.get(p, p) for p in self.entry_patterns]
        state["last_entry_pattern"] = self._last_entry_pattern
        state["last_entry_pattern_price"] = self._last_entry_pattern_price
        state["entry_pattern_detected"] = self._entry_pattern_detected
        state["entry_trigger_armed"] = self._entry_trigger_armed
        state["candles_since_entry_signal"] = self._candles_since_entry_signal

        # Exit patterns info (list)
        state["exit_patterns"] = self.exit_patterns
        state["exit_patterns_labels"] = [pattern_labels.get(p, p) for p in self.exit_patterns] if self.exit_patterns else ["사용하지 않음"]
        state["last_exit_pattern"] = self._last_exit_pattern
        state["last_exit_pattern_price"] = self._last_exit_pattern_price
        state["exit_pattern_detected"] = self._exit_pattern_detected

        # Common info
        state["cooldown"] = self.cooldown
        state["lookback"] = self.lookback
        state["history_size"] = len(self._candle_history)

        # Last detected pattern labels
        if self._last_entry_pattern:
            state["entry_pattern_label"] = pattern_labels.get(self._last_entry_pattern, self._last_entry_pattern)

        if self._last_exit_pattern:
            state["exit_pattern_label"] = pattern_labels.get(self._last_exit_pattern, self._last_exit_pattern)

        return state
