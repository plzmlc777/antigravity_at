"""
Composer ABC — anything that learns features → predicted forward return.

Implementations:
  - LGBMComposerAdapter (in composers/lgbm.py): wraps existing LGBMComposer
  - LinearComposer / EnsembleComposer / NeuralComposer: future

The composer is OBLIVIOUS to which sources produced the features. It only sees
the concatenated feature matrix.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pandas as pd


class Composer(ABC):
    """Fit a model from feature_matrix + target → predict on new features."""

    @abstractmethod
    def fit(self, features: pd.DataFrame, target: pd.Series) -> None:
        """Train. `features` columns are arbitrary (set by upstream Pipeline).
        `target` index aligns with `features.index`. NaN handling is the
        composer's responsibility."""
        raise NotImplementedError

    @abstractmethod
    def predict(self, features: pd.DataFrame) -> np.ndarray:
        """Return 1-D np.ndarray of predictions, length == len(features)."""
        raise NotImplementedError

    def feature_importances(self) -> pd.Series | None:
        """Optional. If the composer can report importances, return Series
        indexed by feature name. Else return None (default)."""
        return None

    @property
    def is_fitted(self) -> bool:
        """Subclasses should override or set an internal flag."""
        return getattr(self, "_fitted", False)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(fitted={self.is_fitted})>"
