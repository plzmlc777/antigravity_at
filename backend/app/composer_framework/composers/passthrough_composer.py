"""NegationPassthroughComposer — no-ML composer for rule-based paradigms.

Designed for `funding_carry`: BinanceFundingZScoreSource emits a single
`bnfz_zscore` feature, and FundingReversalPolicy needs the negation of that
z-score as its prediction (positive z = crowd long = expect reversal down,
so prediction should drive a SHORT entry → prediction < 0 → policy enters short
when prediction < -entry_threshold).

Behavior:
  - fit(): no-op (always reports as fitted)
  - predict(): emit `-1.0 * features[feature_col]` (or 0.0 when NaN)

Use with `policy.long_short_threshold` (or `funding_reversal`):
  - z = +3 → prediction = -3 → enter SHORT (assuming entry_threshold ~0.5)
  - z = -3 → prediction = +3 → enter LONG
  - |z| < entry_threshold → no entry
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.composer_framework.composer import Composer


class NegationPassthroughComposer(Composer):
    """Passthrough composer with sign negation. No fitting required."""

    def __init__(self, feature_col: str = "bnfz_zscore", scale: float = 1.0) -> None:
        self.feature_col = feature_col
        self.scale = float(scale)
        self._fitted = True  # always

    def fit(self, features: pd.DataFrame, target: pd.Series) -> None:
        # No-op. Mark as fitted (already True) so downstream Pipeline checks pass.
        self._fitted = True

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        if self.feature_col not in features.columns:
            # Tolerant fallback: try any column starting with the feature_col
            # prefix (e.g. someone passes `bnfz_zscore_v2`).
            candidates = [c for c in features.columns if c.startswith(self.feature_col)]
            if not candidates:
                return np.zeros(len(features))
            col = candidates[0]
        else:
            col = self.feature_col

        z = features[col].astype(float).values
        # NaN → 0 (no signal); negate sign; apply scale
        z = np.where(np.isnan(z), 0.0, z)
        return -self.scale * z

    def feature_importances(self):
        return None


class PassthroughComposer(Composer):
    """Pass-through composer (no negation). Predicts feature_col directly.

    Designed for `autocorr_regime`: BinanceAutocorrRegimeSource emits a discrete
    `bnar_signal` in {-1, 0, +1} where +1 = LONG signal, -1 = SHORT signal.
    The policy reads prediction sign directly:
      - prediction > +entry_threshold → enter LONG
      - prediction < -entry_threshold → enter SHORT

    Use with `long_short_threshold` (entry_threshold=0.5) or
    `funding_reversal` (entry_threshold=0.5, exit_threshold=0).
    """

    def __init__(self, feature_col: str = "bnar_signal", scale: float = 1.0) -> None:
        self.feature_col = feature_col
        self.scale = float(scale)
        self._fitted = True

    def fit(self, features: pd.DataFrame, target: pd.Series) -> None:
        self._fitted = True

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        if self.feature_col not in features.columns:
            candidates = [c for c in features.columns if c.startswith(self.feature_col)]
            if not candidates:
                return np.zeros(len(features))
            col = candidates[0]
        else:
            col = self.feature_col
        z = features[col].astype(float).values
        z = np.where(np.isnan(z), 0.0, z)
        return self.scale * z

    def feature_importances(self):
        return None
