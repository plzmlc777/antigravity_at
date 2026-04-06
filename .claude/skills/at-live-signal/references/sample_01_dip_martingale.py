"""
[샘플] Dip Martingale Strategy — 가장 단순한 MartingaleBase 전략.

난이도: 쉬움
진입: 캔들 시가 대비 N% 하락 시 LONG
추가진입: 캔들 시가 대비 M% 하락 시
청산: MartingaleBase 기본 (트레일링 스탑, 손절)
LONG/SHORT: LONG only

핵심 포인트:
- _check_entry_trigger → Side.LONG 또는 None
- _check_additional_trigger → True 또는 False
- 지표 계산 없음, 단순 가격 비교
- PARAMETER_SCHEMA fields + COMMON_PARAMETER_FIELDS
"""

from typing import Dict, Any, Optional
from .base import BaseStrategy
from .martingale_base import MartingaleBase
from ..core.constants import Side


class DipMartingaleStrategy(MartingaleBase):
    """
    Dip Martingale Strategy
    - Buy trigger: When a candle drops dip_percent% from its open price.
    - Additional entries: When a candle drops level_gap_percent% from its open.
    - All position management, trailing stop, HODL inherited from MartingaleBase.
    """

    PARAMETER_SCHEMA = {
        "fields": [
            {"name": "dip_percent", "type": "number", "label": "Dip Threshold (%)",
             "default": 1.0, "min": 0.1, "max": 20, "step": 0.1,
             "description": "Initial dip % from candle open to trigger L1 entry",
             "show_in_table": True, "defaultOptRange": "0.5, 1.0, 1.5, 2.0"},
            {"name": "level_gap_percent", "type": "number", "label": "Level Gap (%)",
             "default": 2.0, "min": 0.5, "max": 20, "step": 0.5,
             "description": "Price drop % from candle open to trigger L2+ entries",
             "show_in_table": True, "defaultOptRange": "1.0, 2.0, 3.0"},
        ] + BaseStrategy.COMMON_PARAMETER_FIELDS
    }

    def _initialize_trigger(self):
        """Initialize dip-specific parameters."""
        self.dip_percent = self.config.get("dip_percent", 1.0)
        self.level_gap_percent = self.config.get("level_gap_percent", 2.0)

    def _check_entry_trigger(self, data: Dict[str, Any]) -> Optional[str]:
        """L1: candle drops dip_percent% from its open."""
        current_price = data['close']
        candle_open = data.get('open', current_price)
        candle_drop = (candle_open - current_price) / candle_open if candle_open > 0 else 0
        return Side.LONG if candle_drop >= (self.dip_percent / 100) else None

    def _check_additional_trigger(self, data: Dict[str, Any]) -> bool:
        """L2+: candle drops level_gap_percent% from its open."""
        current_price = data['close']
        candle_open = data.get('open', current_price)
        candle_drop = (candle_open - current_price) / candle_open if candle_open > 0 else 0
        return candle_drop >= (self.level_gap_percent / 100)

    @property
    def _log_prefix(self) -> str:
        return "DipMartingale"

    @property
    def _strategy_id(self) -> str:
        return "dip_martingale"

    def get_state(self) -> Dict[str, Any]:
        state = super().get_state()
        state["target_dip"] = self.dip_percent / 100.0
        return state
