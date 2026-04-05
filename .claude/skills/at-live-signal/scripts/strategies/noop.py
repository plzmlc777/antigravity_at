"""
NoOpStrategy — Skill-only mode.
Generates zero signals — all signals come from external skills or API.
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
