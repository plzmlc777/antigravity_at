"""XGBComposerAdapter — XGBoost regressor with the Composer ABC interface."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.composer_framework.composer import Composer


class XGBComposerAdapter(Composer):
    """Drop-in alternative to LGBMComposerAdapter.

    Constructor kwargs override the default hyperparameters; otherwise uses
    a conservative regularized config matching the ablation study setup.
    """

    DEFAULTS: dict = {
        "n_estimators": 300,
        "learning_rate": 0.03,
        "max_depth": 5,
        "subsample": 0.9,
        "colsample_bytree": 0.9,
        "reg_alpha": 0.1,
        "reg_lambda": 0.1,
        "random_state": 42,
        "verbosity": 0,
    }

    def __init__(self, **kwargs) -> None:
        import xgboost as xgb
        self._xgb = xgb
        self._params = {**self.DEFAULTS, **kwargs}
        self.model = None
        self._feature_names: list[str] | None = None
        self._fitted = False

    def fit(self, features: pd.DataFrame, target: pd.Series) -> None:
        df = features.copy()
        df["__target__"] = target
        df = df.dropna(subset=["__target__"])
        feat_cols = [c for c in df.columns if c != "__target__"]
        df[feat_cols] = df[feat_cols].fillna(0.0)
        X, y = df[feat_cols].values, df["__target__"].values
        self.model = self._xgb.XGBRegressor(**self._params)
        self.model.fit(X, y)
        self._feature_names = feat_cols
        self._fitted = True

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        if self.model is None or self._feature_names is None:
            raise RuntimeError("XGBComposerAdapter.predict called before fit")
        df = features.copy()
        for c in self._feature_names:
            if c not in df.columns:
                df[c] = 0.0
        df = df[self._feature_names].fillna(0.0)
        return self.model.predict(df.values)

    def feature_importances(self) -> pd.Series | None:
        if self.model is None or self._feature_names is None:
            return None
        try:
            return pd.Series(
                self.model.feature_importances_,
                index=self._feature_names,
            ).sort_values(ascending=False)
        except Exception:
            return None
