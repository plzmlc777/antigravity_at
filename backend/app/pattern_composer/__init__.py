"""
Pattern Composer — Layer 5 of the AI-native pattern strategy system.

Reads:
  - Live PatternScanner output (signals at TF timestamps)
  - Live RegimeClassifier output (regime per bar per TF)
  - Trained FitnessTensor (which (pattern, tf, regime, direction) cells have edge)

Decides:
  - At each evaluation moment, which active signals are credible right now
  - Composes them into a single ensemble score (direction + magnitude + confidence)
  - Emits Entry / Hold / Exit decisions

This module also provides a simple Backtester that walks 1m bars and simulates
trading according to a Composer's decisions, returning KPIs.

See .claude/plans/pattern_strategy_master.json (architecture.layer_5_dynamic_composer).
"""
from .types import (
    BacktestResult,
    ComposerDecision,
    Trade,
)
from .composer import DynamicPatternComposer, ComposerConfig
from .backtest import Backtester
from .event_backtest import EventDrivenBacktester, EventBacktestConfig
from .multi_backtest import MultiPositionEventBacktester, MultiBacktestConfig
from .floor_backtest import PositionFloorBacktester, FloorBacktestConfig
from .defensive_backtest import DefensiveTimingBacktester, DefensiveConfig
from .adaptive_backtest import RegimeAdaptiveBacktester, AdaptiveConfig

__all__ = [
    "BacktestResult",
    "ComposerDecision",
    "Trade",
    "DynamicPatternComposer",
    "ComposerConfig",
    "Backtester",
    "EventDrivenBacktester",
    "EventBacktestConfig",
    "MultiPositionEventBacktester",
    "MultiBacktestConfig",
    "PositionFloorBacktester",
    "FloorBacktestConfig",
    "DefensiveTimingBacktester",
    "DefensiveConfig",
    "RegimeAdaptiveBacktester",
    "AdaptiveConfig",
]
