"""
Regime Classifier — Layer 3 of the AI-native pattern strategy system.

See .claude/plans/pattern_strategy_master.json (architecture.layer_3_regime_classifier).

Continuous OHLCV → 4-dim regime vector (trend × volatility × liquidity × momentum),
each dim discretized into 3 buckets → 3^4 = 81 cells (sparse in practice).

The fitness tensor (Phase 4) is keyed by (pattern, timeframe, regime_cell), so
the classifier is the bridge that turns a continuous market state into a
discrete address in fitness space.
"""
from .classifier import (
    LIQUIDITY_LABELS,
    MOMENTUM_LABELS,
    REGIME_DIMS,
    RegimeClassifier,
    RegimeVector,
    TREND_LABELS,
    VOLATILITY_LABELS,
)
from .features import (
    compute_liquidity_score,
    compute_momentum_score,
    compute_trend_score,
    compute_volatility_score,
)

__all__ = [
    "LIQUIDITY_LABELS",
    "MOMENTUM_LABELS",
    "REGIME_DIMS",
    "RegimeClassifier",
    "RegimeVector",
    "TREND_LABELS",
    "VOLATILITY_LABELS",
    "compute_liquidity_score",
    "compute_momentum_score",
    "compute_trend_score",
    "compute_volatility_score",
]
