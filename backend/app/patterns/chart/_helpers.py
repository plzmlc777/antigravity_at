"""Shared geometric utilities for chart patterns."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import find_peaks


def atr_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period, min_periods=1).mean()


def find_peaks_arr(arr: np.ndarray, prominence: float, distance: int) -> np.ndarray:
    peaks, _ = find_peaks(arr, prominence=prominence, distance=distance)
    return peaks


def find_troughs_arr(arr: np.ndarray, prominence: float, distance: int) -> np.ndarray:
    troughs, _ = find_peaks(-arr, prominence=prominence, distance=distance)
    return troughs


def linreg_slope(y: np.ndarray) -> tuple[float, float]:
    """Return (slope, intercept) for y vs index."""
    x = np.arange(len(y))
    if len(y) < 2:
        return 0.0, float(y[0]) if len(y) else 0.0
    slope, intercept = np.polyfit(x, y, 1)
    return float(slope), float(intercept)
