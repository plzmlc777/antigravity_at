"""
[샘플] Chart Pattern Strategy — 차트 패턴 인식 전략.

난이도: 어려움
진입: 선택한 패턴(double_bottom, v_bottom, triangle, wedge) 감지 시 LONG
추가진입: 동일 패턴 재발동
청산: _check_exit_trigger로 매도 패턴 감지 (double_top, v_top 등)
LONG/SHORT: LONG only (패턴 기반)

핵심 포인트:
- "multiselect" 타입 파라미터 (복수 선택 → 쉼표 구분 문자열)
- OR 로직: 선택한 패턴 중 하나라도 감지되면 트리거
- 6가지 패턴 알고리즘 (double_bottom, v_bottom, double_top, v_top, triangle, wedge)
- entry_patterns / exit_patterns 분리
- cooldown_candles로 과다 매매 방지
- customize_fields로 COMMON 기본값 오버라이드
- 가장 긴 전략 (~626줄) — 패턴 감지 알고리즘이 핵심
"""

from typing import Dict, Any, List, Optional
from collections import deque
from .base import BaseStrategy, customize_fields
from .martingale_base import MartingaleBase
from ..core.constants import Side


class ChartPatternStrategy(MartingaleBase):
    """
    Chart Pattern Detection Strategy
    - double_bottom: W 패턴 (두 바닥 + 넥라인 돌파)
    - v_bottom: V자 반등 (급락 → 급반등)
    - double_top: M 패턴 (매도용, 두 고점 + 넥라인 이탈)
    - v_top: 역V (매도용, 급등 → 급락)
    - triangle: 수렴 삼각형 (상단/하단 돌파)
    - wedge: 쐐기 패턴 (falling wedge = 매수, rising wedge = 매도)
    """

    PARAMETER_SCHEMA = {
        "fields": [
            # ★ multiselect: 복수 선택 가능, 쉼표 구분 문자열로 전달
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
                "description": "복수 선택 가능 (OR 로직)",
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
                "description": "선택 안하면 트레일링 스탑만 사용",
                "show_in_table": True,
            },
            {"name": "lookback_candles", "type": "number", "label": "Lookback Candles",
             "default": 20, "min": 10, "max": 100, "step": 5,
             "description": "Pattern detection lookback period",
             "show_in_table": True, "defaultOptRange": "15, 20, 30, 50"},
            {"name": "tolerance_percent", "type": "number", "label": "Tolerance (%)",
             "default": 1.5, "min": 0.5, "max": 5.0, "step": 0.1,
             "description": "Price similarity tolerance for pattern matching",
             "show_in_table": True, "defaultOptRange": "1.0, 1.5, 2.0, 3.0"},
            {"name": "min_pattern_depth", "type": "number", "label": "Min Pattern Depth (%)",
             "default": 3.0, "min": 1.0, "max": 20.0, "step": 0.5,
             "description": "Minimum price swing % required for valid pattern",
             "show_in_table": True, "defaultOptRange": "2.0, 3.0, 5.0, 7.0"},
            {"name": "breakout_confirm", "type": "select", "label": "Breakout Confirmation",
             "default": "immediate",
             "options": ["immediate", "close_above", "volume_confirm"],
             "show_in_table": True},
            {"name": "cooldown_candles", "type": "number", "label": "Cooldown Candles",
             "default": 5, "min": 0, "max": 50, "step": 1,
             "description": "Minimum candles between pattern signals",
             "show_in_table": False, "defaultOptRange": "3, 5, 10"},
        ] + customize_fields(BaseStrategy.COMMON_PARAMETER_FIELDS, {
            "max_buy_count": {"default": 3},
            "trailing_start_percent": {"default": 5.0},
            "trailing_stop_percent": {"default": 2.0},
        })
    }

    def _initialize_trigger(self):
        # ★ multiselect 파싱: 쉼표 구분 문자열 → 리스트
        entry_raw = self.config.get("entry_patterns", "double_bottom")
        if isinstance(entry_raw, str):
            self.entry_patterns = [p.strip() for p in entry_raw.split(",") if p.strip()]
        elif isinstance(entry_raw, list):
            self.entry_patterns = [p for p in entry_raw if p]
        else:
            self.entry_patterns = ["double_bottom"]
        if not self.entry_patterns:
            self.entry_patterns = ["double_bottom"]

        exit_raw = self.config.get("exit_patterns", "")
        if isinstance(exit_raw, str):
            self.exit_patterns = [p.strip() for p in exit_raw.split(",") if p.strip()]
        elif isinstance(exit_raw, list):
            self.exit_patterns = [p for p in exit_raw if p]
        else:
            self.exit_patterns = []

        self.lookback = int(self.config.get("lookback_candles", 20))
        self.tolerance = float(self.config.get("tolerance_percent", 1.5)) / 100.0
        self.min_depth = float(self.config.get("min_pattern_depth", 3.0)) / 100.0
        self.breakout_confirm = self.config.get("breakout_confirm", "immediate")
        self.cooldown = int(self.config.get("cooldown_candles", 5))
        self._candle_history: deque = deque(maxlen=self.lookback + 10)
        self._last_entry_pattern: Optional[str] = None
        self._candles_since_entry_signal: int = 999
        self._entry_trigger_armed: bool = True

    def preload_history(self, candles: list):
        needed = self.lookback + 5
        recent = candles[-needed:] if len(candles) >= needed else candles
        for candle in recent:
            self._candle_history.append({
                'open': candle.get('open', 0), 'high': candle.get('high', 0),
                'low': candle.get('low', 0), 'close': candle.get('close', 0),
                'volume': candle.get('volume', 0),
            })

    def _on_candle(self, data: Dict[str, Any]):
        self._candle_history.append({
            'open': data.get('open', data['close']), 'high': data.get('high', data['close']),
            'low': data.get('low', data['close']), 'close': data['close'],
            'volume': data.get('volume', 0),
        })
        self._candles_since_entry_signal += 1
        if not self._entry_trigger_armed and self._candles_since_entry_signal >= self.cooldown:
            self._entry_trigger_armed = True

    def _check_entry_trigger(self, data: Dict[str, Any]) -> Optional[str]:
        if not self._entry_trigger_armed or len(self._candle_history) < self.lookback:
            return None
        candles = list(self._candle_history)[-self.lookback:]
        detected = self._detect_entry_pattern(candles, data['close'])
        if detected:
            self._last_entry_pattern = detected
            self._candles_since_entry_signal = 0
            self._entry_trigger_armed = False
            return Side.LONG
        return None

    def _check_additional_trigger(self, data: Dict[str, Any]) -> bool:
        return self._check_entry_trigger(data)

    def _check_exit_trigger(self, data: Dict[str, Any]) -> bool:
        if not self.exit_patterns or len(self._candle_history) < self.lookback:
            return False
        candles = list(self._candle_history)[-self.lookback:]
        return self._detect_exit_pattern(candles, data['close']) is not None

    # ── 패턴 감지 알고리즘 (핵심 로직) ──

    def _detect_entry_pattern(self, candles: List[dict], current_price: float) -> Optional[str]:
        """OR 로직: 선택한 패턴 중 하나라도 감지되면 반환."""
        detectors = {
            "double_bottom": lambda: self._detect_double_bottom(candles, current_price),
            "v_bottom": lambda: self._detect_v_bottom(candles, current_price),
            "triangle": lambda: self._detect_triangle(candles, current_price, "up"),
            "wedge": lambda: self._detect_wedge(candles, current_price, "up"),
        }
        for pattern in self.entry_patterns:
            if pattern in detectors:
                result = detectors[pattern]()
                if result:
                    return result
        return None

    def _detect_exit_pattern(self, candles: List[dict], current_price: float) -> Optional[str]:
        detectors = {
            "double_top": lambda: self._detect_double_top(candles, current_price),
            "v_top": lambda: self._detect_v_top(candles, current_price),
            "triangle": lambda: self._detect_triangle(candles, current_price, "down"),
            "wedge": lambda: self._detect_wedge(candles, current_price, "down"),
        }
        for pattern in self.exit_patterns:
            if pattern in detectors:
                result = detectors[pattern]()
                if result:
                    return result
        return None

    def _detect_double_bottom(self, candles: List[dict], current_price: float) -> Optional[str]:
        """W 패턴: 두 비슷한 저점 + 중간 고점(넥라인) 돌파."""
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
        left, right = min(min_idx1, min_idx2), max(min_idx1, min_idx2)
        if right - left < 3:
            return None
        neckline = max(highs[left:right+1])
        if (neckline - avg_low) / neckline < self.min_depth:
            return None
        if current_price > neckline:
            return "double_bottom"
        return None

    def _detect_v_bottom(self, candles: List[dict], current_price: float) -> Optional[str]:
        """V자 반등: 급락 → 급반등."""
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
        if current_price > candles[min_idx]['close'] * (1 + self.min_depth * 0.5):
            return "v_bottom"
        return None

    def _detect_double_top(self, candles: List[dict], current_price: float) -> Optional[str]:
        """M 패턴 (매도용): 두 고점 + 넥라인 이탈."""
        highs = [c['high'] for c in candles]
        lows = [c['low'] for c in candles]
        max_idx1 = highs.index(max(highs))
        second_highs = [(i, highs[i]) for i in range(len(highs)) if abs(i - max_idx1) >= 3]
        if not second_highs:
            return None
        max_idx2, max_val2 = max(second_highs, key=lambda x: x[1])
        avg_high = (highs[max_idx1] + max_val2) / 2
        if abs(highs[max_idx1] - max_val2) / avg_high > self.tolerance:
            return None
        left, right = min(max_idx1, max_idx2), max(max_idx1, max_idx2)
        if right - left < 3:
            return None
        neckline = min(lows[left:right+1])
        if (avg_high - neckline) / avg_high < self.min_depth:
            return None
        if current_price < neckline:
            return "double_top"
        return None

    def _detect_v_top(self, candles: List[dict], current_price: float) -> Optional[str]:
        """역V (매도용): 급등 → 급락."""
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
        if current_price < candles[max_idx]['close'] * (1 - self.min_depth * 0.5):
            return "v_top"
        return None

    def _detect_triangle(self, candles: List[dict], current_price: float, direction: str) -> Optional[str]:
        """수렴 삼각형: 변동폭 감소 → 돌파."""
        highs = [c['high'] for c in candles]
        lows = [c['low'] for c in candles]
        half = len(candles) // 2
        first_range = max(highs[:half]) - min(lows[:half])
        second_range = max(highs[half:]) - min(lows[half:])
        if second_range >= first_range * 0.9:
            return None
        if direction == "up" and current_price > max(highs[-3:]):
            return "triangle_up"
        elif direction == "down" and current_price < min(lows[-3:]):
            return "triangle_down"
        return None

    def _detect_wedge(self, candles: List[dict], current_price: float, direction: str) -> Optional[str]:
        """쐐기 패턴: 선형회귀로 고점/저점 기울기 비교."""
        highs = [c['high'] for c in candles]
        lows = [c['low'] for c in candles]
        n = len(candles)
        x_sum = sum(range(n))
        x2_sum = sum(i*i for i in range(n))
        denom = n * x2_sum - x_sum * x_sum
        if denom == 0:
            return None
        high_slope = (n * sum(i*highs[i] for i in range(n)) - x_sum * sum(highs)) / denom
        low_slope = (n * sum(i*lows[i] for i in range(n)) - x_sum * sum(lows)) / denom
        if direction == "up" and high_slope < 0 and low_slope < 0:
            if current_price > max(highs[-3:]):
                return "falling_wedge"
        elif direction == "down" and high_slope > 0 and low_slope > 0:
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
        state["entry_patterns"] = self.entry_patterns
        state["exit_patterns"] = self.exit_patterns
        state["last_entry_pattern"] = self._last_entry_pattern
        state["entry_trigger_armed"] = self._entry_trigger_armed
        state["lookback"] = self.lookback
        state["history_size"] = len(self._candle_history)
        return state
