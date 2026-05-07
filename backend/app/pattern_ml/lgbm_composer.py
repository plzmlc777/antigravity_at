"""LightGBM-based composer.

Trains a regression model to predict forward N-bar return from the feature
matrix. At inference time, the predicted return is used as a continuous "edge
score" — positive → long, negative → short (if allowed), magnitude → conviction.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class LGBMComposerConfig:
    n_estimators: int = 300
    learning_rate: float = 0.03
    max_depth: int = 5
    num_leaves: int = 31
    min_child_samples: int = 20
    reg_alpha: float = 0.1
    reg_lambda: float = 0.1
    feature_fraction: float = 0.9
    bagging_fraction: float = 0.9
    bagging_freq: int = 5
    random_state: int = 42


class LGBMComposer:
    """Wraps lightgbm.LGBMRegressor with our feature/target convention.

    Public API:
      - fit(features_df, target_col='target_fwd_ret')
      - predict(features_df) → np.ndarray of predicted forward returns
      - feature_importances() → pd.Series
    """

    def __init__(self, config: LGBMComposerConfig | None = None) -> None:
        try:
            import lightgbm as lgb  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "lightgbm not installed — pip install lightgbm in backend venv"
            ) from e
        self.config = config or LGBMComposerConfig()
        self.model = None
        self._feature_names: list[str] | None = None

    def fit(self, features_df: pd.DataFrame, target_col: str = "target_fwd_ret") -> None:
        import lightgbm as lgb

        df = features_df.dropna(subset=[target_col]).copy()
        # Drop rows with too many NaN features (keep partial)
        feature_cols = [c for c in df.columns if c != target_col]
        df = df.dropna(subset=feature_cols, how="all")
        # Fill remaining NaN with 0 (most pattern counts are 0 by default anyway)
        df[feature_cols] = df[feature_cols].fillna(0.0)

        X = df[feature_cols].values
        y = df[target_col].values
        cfg = self.config
        self.model = lgb.LGBMRegressor(
            n_estimators=cfg.n_estimators,
            learning_rate=cfg.learning_rate,
            max_depth=cfg.max_depth,
            num_leaves=cfg.num_leaves,
            min_child_samples=cfg.min_child_samples,
            reg_alpha=cfg.reg_alpha,
            reg_lambda=cfg.reg_lambda,
            feature_fraction=cfg.feature_fraction,
            bagging_fraction=cfg.bagging_fraction,
            bagging_freq=cfg.bagging_freq,
            random_state=cfg.random_state,
            verbose=-1,
        )
        self.model.fit(X, y)
        self._feature_names = feature_cols

    def predict(self, features_df: pd.DataFrame) -> np.ndarray:
        if self.model is None or self._feature_names is None:
            raise RuntimeError("Model not fitted")
        df = features_df.copy()
        # ensure all feature cols are present
        for c in self._feature_names:
            if c not in df.columns:
                df[c] = 0.0
        df = df[self._feature_names].fillna(0.0)
        return self.model.predict(df.values)

    def feature_importances(self) -> pd.Series:
        if self.model is None or self._feature_names is None:
            raise RuntimeError("Model not fitted")
        return pd.Series(self.model.feature_importances_, index=self._feature_names).sort_values(ascending=False)
