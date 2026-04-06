"""
[샘플] NoOp Strategy — 스킬 전용 빈 전략.

난이도: 특수 (스킬 전용)
진입: 없음 (시그널 0)
청산: 없음
용도: 외부 스킬/API가 submit_external_signal()로 시그널 주입

핵심 포인트:
- BaseStrategy 직접 상속 (MartingaleBase가 아님!)
- initialize(), on_data() 모두 빈 구현
- PARAMETER_SCHEMA에 COMMON_PARAMETER_FIELDS 없음
- strategy_name: "noop" + engine_version: "v2" 로 세션 생성
"""

from typing import Dict, Any
from .base import BaseStrategy


class NoOpStrategy(BaseStrategy):
    """No-operation strategy. Generates zero signals — skill-only mode."""

    PARAMETER_SCHEMA = {
        "name": "No-Op (Skill Only)",
        "description": "Generates no signals. Use with external skill signals only.",
        "fields": [
            {"name": "interval", "type": "select", "label": "Interval",
             "default": "1m",
             "options": ["1m", "3m", "5m", "15m", "30m", "60m"],
             "description": "Candle interval for skill analysis",
             "group": "common"},
        ],
    }

    def initialize(self):
        pass

    def on_data(self, candle: Dict[str, Any]):
        pass
