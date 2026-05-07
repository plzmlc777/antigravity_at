"""
Pattern Library — Detection primitives for the AI-native pattern strategy system.

See .claude/plans/pattern_strategy_master.json for architecture.

Layer 1 of 6. Each detector is a pure function:
    ohlcv DataFrame -> list[PatternSignal]

Detectors must NOT contain trading logic (SL/TP/sizing). That belongs to Layer 5
(DynamicPatternComposer). Detectors only emit signals + suggested levels.
"""
from .base import (
    PatternCategory,
    PatternDetector,
    PatternDirection,
    PatternSignal,
)
from .registry import PatternRegistry

__all__ = [
    "PatternCategory",
    "PatternDetector",
    "PatternDirection",
    "PatternSignal",
    "PatternRegistry",
]
