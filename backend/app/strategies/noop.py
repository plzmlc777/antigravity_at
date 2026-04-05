"""
NoOpStrategy — 스킬 전용 모드용 빈 전략.

시그널을 전혀 생성하지 않으며, 외부 소스(스킬, API)만
SignalInterceptContext.submit_external_signal()을 통해 시그널을 주입합니다.

사용법:
    strategy_name: "noop"
    engine_version: "v2"  (필수)
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
        # Intentionally empty — all signals come from external skills
        pass
