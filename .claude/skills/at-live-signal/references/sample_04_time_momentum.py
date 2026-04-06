"""
[샘플] Time Momentum Strategy — 시간 기반 일일 전략.

난이도: 보통
진입: start_time + delay_minutes 후 가격 변동률이 target_percent 이상 시 LONG
추가진입: 없음 (max_buy_count=1)
청산: stop_time 강제 청산 + MartingaleBase 트레일링 스탑
LONG/SHORT: LONG only

핵심 포인트:
- customize_fields()로 COMMON_PARAMETER_FIELDS 기본값 오버라이드
- "time" 타입 파라미터 (HH:MM 형식)
- _on_candle에서 일일 리셋 + 레퍼런스 가격 캡처 + stop_time 강제 청산
- checked_today 가드로 하루 한 번만 진입
- context.get_time()으로 현재 시간 조회
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from .base import BaseStrategy, customize_fields
from .martingale_base import MartingaleBase
from ..core.constants import Side


class TimeMomentumStrategy(MartingaleBase):
    """
    Time Momentum Strategy
    - At start_time, capture daily reference price.
    - At start_time + delay_minutes, check if price change >= target_percent.
    - Force sell at stop_time.
    - One trade per day.
    """

    PARAMETER_SCHEMA = {
        "fields": [
            {"name": "start_time", "type": "time", "label": "Start Time",
             "default": "09:00",
             "description": "Time to start monitoring price",
             "show_in_table": True},
            {"name": "stop_time", "type": "time", "label": "Stop Time",
             "default": "15:00",
             "description": "Force exit time",
             "show_in_table": True},
            {"name": "delay_minutes", "type": "number", "label": "Delay (min)",
             "default": 10, "min": 0, "max": 120, "step": 1,
             "description": "Wait minutes after start before entry check",
             "show_in_table": True, "defaultOptRange": "5, 10, 30, 60"},
            {"name": "direction", "type": "select", "label": "Direction",
             "default": "rise", "options": ["rise", "fall"],
             "description": "rise=momentum buy, fall=dip buy",
             "show_in_table": True},
            {"name": "target_percent", "type": "number", "label": "Target (%)",
             "default": 2.0, "min": 0.1, "max": 20, "step": 0.1,
             "description": "Min price change % to trigger buy",
             "show_in_table": True, "defaultOptRange": "1.0, 2.0, 3.0, 5.0"},
            # ★ customize_fields: COMMON 기본값을 전략에 맞게 오버라이드
        ] + customize_fields(BaseStrategy.COMMON_PARAMETER_FIELDS, {
            "max_buy_count": {"default": 1},
            "last_level_allin": {"default": "on"},
            "trailing_start_percent": {"default": 5.0, "defaultOptRange": "1.0, 3.0, 5.0, 10.0"},
            "trailing_stop_percent": {"default": 2.0, "defaultOptRange": "0.5, 1.0, 2.0, 3.0"},
            "max_loss_percent": {"default": 3.0, "defaultOptRange": "2.0, 3.0, 5.0"},
        })
    }

    def _initialize_trigger(self):
        self.start_time_str = self.config.get("start_time") or "09:00"
        self.stop_time_str = self.config.get("stop_time") or "15:00"
        try:
            self.start_time = datetime.strptime(self.start_time_str, "%H:%M").time()
        except ValueError:
            self.start_time = datetime.strptime("09:00", "%H:%M").time()
        try:
            self.stop_time = datetime.strptime(self.stop_time_str, "%H:%M").time()
        except ValueError:
            self.stop_time = datetime.strptime("15:00", "%H:%M").time()
        self.delay_minutes = int(self.config.get("delay_minutes", 10) or 10)
        self.direction = self.config.get("direction", "rise")
        raw_target = float(self.config.get("target_percent", 2.0) or 2.0)
        self.target_percent = abs(raw_target) / 100.0
        self.checked_today = False
        self.daily_reference_price = None
        self._daily_date = None

    def _on_candle(self, data: Dict[str, Any]):
        """일일 리셋 + 레퍼런스 가격 캡처 + stop_time 강제 청산."""
        current_time = self.context.get_time()
        current_date = current_time.date()
        current_price = data['close']

        # 1. Daily reset
        if self._daily_date != current_date:
            self._daily_date = current_date
            self.checked_today = False
            self.daily_reference_price = None

        # 2. Capture reference price at start_time
        if current_time.time() >= self.start_time and self.daily_reference_price is None:
            self.daily_reference_price = current_price

        # 3. Force liquidation at stop_time
        if self.current_level > 0 and current_time.time() >= self.stop_time:
            self._liquidate(current_price)
            self.checked_today = True

    def _check_entry_trigger(self, data: Dict[str, Any]) -> Optional[str]:
        """하루 한 번, start_time + delay 후 가격 변동 체크."""
        if self.checked_today or self.daily_reference_price is None:
            return None
        current_time = self.context.get_time()
        trigger_time = datetime.combine(current_time.date(), self.start_time) + timedelta(minutes=self.delay_minutes)
        if current_time < trigger_time:
            return None
        self.checked_today = True
        current_price = data['close']
        change = (current_price - self.daily_reference_price) / self.daily_reference_price
        if self.direction == "fall":
            should_buy = change <= -self.target_percent
        else:
            should_buy = change >= self.target_percent
        return Side.LONG if should_buy else None

    def _check_additional_trigger(self, data: Dict[str, Any]) -> bool:
        return False

    @property
    def _log_prefix(self) -> str:
        return "TimeMomentum"

    @property
    def _strategy_id(self) -> str:
        return "time_momentum"

    def get_state(self) -> Dict[str, Any]:
        state = super().get_state()
        state["reference_price"] = self.daily_reference_price
        state["target_percent"] = self.target_percent
        state["direction"] = self.direction
        state["checked_today"] = self.checked_today
        state["start_time"] = self.start_time_str
        state["stop_time"] = self.stop_time_str
        return state
