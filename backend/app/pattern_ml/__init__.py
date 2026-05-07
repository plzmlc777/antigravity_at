"""
Pattern-ML — non-linear composer using LightGBM.

Replaces the discrete "fitness cell lookup + linear sum" decision rule with a
gradient-boosted regression that learns forward returns from a continuous
feature space:
  - Pattern signal aggregates (counts/intensity per category × TF × direction)
  - Regime continuous scores (trend / vol / liquidity / momentum)
  - Market state (recent returns, volatility, volume)
  - Calendar features (day of week, hour)

Hypothesis: the discrete cell formulation overfits because (a) cells have
small samples (b) cell boundaries are arbitrary (c) interactions between
patterns aren't captured. ML can find non-linear interactions and continuous
edges that the cell approach misses, given enough data.

(a) 더 많은 데이터: 크립토 (BTC 540d, ETH/SOL 795d)
(b) 동적 학습: LightGBM with walk-forward retraining
"""
from .features import build_feature_matrix
from .lgbm_composer import LGBMComposer, LGBMComposerConfig
from .ml_backtest import MLPatternBacktester, MLBacktestConfig

__all__ = [
    "build_feature_matrix",
    "LGBMComposer",
    "LGBMComposerConfig",
    "MLPatternBacktester",
    "MLBacktestConfig",
]
