"""
Pattern Scanner — Layer 2 of the AI-native pattern strategy system.

See .claude/plans/pattern_strategy_master.json for architecture.

Reads 1m OHLCV, resamples to multiple timeframes (1m/5m/15m/1h/4h/1d), runs
all PatternDetector instances on each TF, and emits a flat tabular Signal
Tensor (DataFrame).

Composer (Layer 5) consumes this tensor + Regime classifier (Layer 3) +
Fitness tensor (Layer 4) to produce trading decisions.
"""
from .types import ScannedSignal, SUPPORTED_TIMEFRAMES, signal_tensor_columns
from .scanner import PatternScanner
from .cache import SignalTensorCache

__all__ = [
    "ScannedSignal",
    "SUPPORTED_TIMEFRAMES",
    "signal_tensor_columns",
    "PatternScanner",
    "SignalTensorCache",
]
