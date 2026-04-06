"""
[샘플] US Market Follow Strategy — 미국 증시 추종 전략.

난이도: 보통
진입: 전일 미국 증시 변동률 ≥ threshold → 한국 장 시작 시 매수
추가진입: 없음 (하루 1회)
청산: MartingaleBase 트레일링 스탑 + cycle_max_hours
LONG/SHORT: LONG only

핵심 포인트:
- 외부 데이터 의존: us_market 모듈로 Yahoo Finance 데이터 조회
- "combobox" 타입 파라미터 (드롭다운 + 직접 입력 가능)
- preload_history에서 백테스트용 US change map 로드
- _get_us_change(): 라이브 vs 백테스트 분기
- customize_fields로 cycle_max_hours 등 기본값 오버라이드
- 하루 한 번 체크 (checked_today 가드)
"""

from typing import Dict, Any, Optional
from .base import BaseStrategy, customize_fields
from .martingale_base import MartingaleBase
from app.core.us_market_data import us_market
from ..core.constants import Side


class UsMarketFollowStrategy(MartingaleBase):
    """
    US Market Follow Strategy
    - 전일 미국 증시가 N% 이상 변동 시 한국 장 시작에 매수
    - trailing stop, stop loss는 MartingaleBase 기본 기능 활용
    """

    PARAMETER_SCHEMA = {
        "fields": [
            # ★ combobox: 드롭다운 + 직접 입력 가능
            {
                "name": "us_index",
                "type": "combobox",
                "label": "US Index",
                "default": "^GSPC",
                "options": [
                    {"value": "^GSPC", "label": "S&P 500"},
                    {"value": "^IXIC", "label": "NASDAQ"},
                    {"value": "^DJI", "label": "DOW"},
                    {"value": "^SOX", "label": "Philadelphia Semi"},
                ],
                "description": "기준 미국 지수 (Yahoo Finance 심볼 직접 입력 가능)",
                "show_in_table": True,
            },
            {
                "name": "trigger_direction",
                "type": "select",
                "label": "Trigger Direction",
                "default": "above",
                "options": [
                    {"value": "above", "label": "상승 (Above)"},
                    {"value": "below", "label": "하락 (Below)"},
                ],
                "description": "above=미국 상승 시 매수, below=미국 하락 시 매수",
                "show_in_table": True,
            },
            {"name": "us_change_threshold", "type": "number", "label": "US Change Threshold (%)",
             "default": 1.0, "min": 0.1, "max": 10.0, "step": 0.1,
             "description": "미국 증시 변동률 임계값",
             "show_in_table": True, "defaultOptRange": "0.5, 1.0, 1.5, 2.0"},
            {"name": "entry_start_time", "type": "time", "label": "Entry Start Time",
             "default": "09:00",
             "description": "매수 시작 시간 (한국 시간)",
             "show_in_table": True},
        ] + customize_fields(BaseStrategy.COMMON_PARAMETER_FIELDS, {
            "max_buy_count": {"default": 1},
            "last_level_allin": {"default": "on"},
            "trailing_start_percent": {"default": 2.0, "defaultOptRange": "1.0, 2.0, 3.0, 5.0"},
            "trailing_stop_percent": {"default": 1.0, "defaultOptRange": "0.5, 1.0, 1.5, 2.0"},
            "max_loss_percent": {"default": 3.0, "defaultOptRange": "2.0, 3.0, 5.0"},
            "cycle_max_hours": {"default": 6, "defaultOptRange": "2, 4, 6, 8"},
        })
    }

    def _initialize_trigger(self):
        self.us_index = self.config.get("us_index", "^GSPC")
        self.trigger_direction = self.config.get("trigger_direction", "above")
        self.us_change_threshold = float(self.config.get("us_change_threshold", 1.0))
        entry_start_str = self.config.get("entry_start_time", "09:00")
        from datetime import datetime
        try:
            self.entry_start_time = datetime.strptime(entry_start_str, "%H:%M").time()
        except ValueError:
            self.entry_start_time = datetime.strptime("09:00", "%H:%M").time()
        self._daily_date = None
        self._checked_today = False
        self._us_change_today = None
        self._trigger_met = False
        self._us_change_map = None  # 백테스트용

    def preload_history(self, candles: list):
        """★ 백테스트용: 1년치 US 변동률 맵 로드."""
        self._us_change_map = us_market.get_change_map(self.us_index, days=365)

    def _get_us_change(self) -> float:
        """라이브 vs 백테스트 분기."""
        current_time = self.context.get_time()
        if self._us_change_map:
            return us_market.get_change_for_date(
                current_time.strftime("%Y-%m-%d"), self._us_change_map)
        else:
            return us_market.get_change(self.us_index)

    def _on_candle(self, data: Dict[str, Any]):
        current_time = self.context.get_time()
        current_date = current_time.date()
        if self._daily_date != current_date:
            self._daily_date = current_date
            self._checked_today = False
            self._us_change_today = None
            self._trigger_met = False

    def _check_entry_trigger(self, data: Dict[str, Any]) -> Optional[str]:
        if self._checked_today:
            return None
        current_time = self.context.get_time()
        if current_time.time() < self.entry_start_time:
            return None
        if self._us_change_today is None:
            self._us_change_today = self._get_us_change()
        self._checked_today = True
        us_change = self._us_change_today
        threshold = self.us_change_threshold
        if self.trigger_direction == "above":
            self._trigger_met = us_change >= threshold
        elif self.trigger_direction == "below":
            self._trigger_met = us_change <= -threshold
        return Side.LONG if self._trigger_met else None

    def _check_additional_trigger(self, data: Dict[str, Any]) -> bool:
        return False

    @property
    def _log_prefix(self) -> str:
        return "UsMarketFollow"

    @property
    def _strategy_id(self) -> str:
        return "us_market_follow"

    def get_state(self) -> Dict[str, Any]:
        state = super().get_state()
        state["us_index"] = self.us_index
        state["us_change_today"] = self._us_change_today
        state["trigger_met"] = self._trigger_met
        state["checked_today"] = self._checked_today
        return state
