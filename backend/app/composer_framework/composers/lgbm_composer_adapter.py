"""LGBMComposerAdapter — bridges existing LGBMComposer to the Composer ABC."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.composer_framework.composer import Composer
from app.pattern_ml.lgbm_composer import LGBMComposer, LGBMComposerConfig


class LGBMComposerAdapter(Composer):
    def __init__(self, config: LGBMComposerConfig | None = None) -> None:
        self._inner = LGBMComposer(config)
        self._fitted = False

    def fit(self, features: pd.DataFrame, target: pd.Series) -> None:
        df = features.copy()
        df["__target__"] = target
        df = df.dropna(subset=["__target__"])
        self._inner.fit(df, target_col="__target__")
        self._fitted = True

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        return self._inner.predict(features)

    def feature_importances(self) -> pd.Series | None:
        try:
            return self._inner.feature_importances()
        except Exception:
            return None
