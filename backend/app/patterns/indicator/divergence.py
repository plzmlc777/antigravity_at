"""RSI / MACD bullish & bearish divergences.

Bullish divergence : price makes a lower low, but indicator makes a higher low.
Bearish divergence : price makes a higher high, but indicator makes a lower high.

Algorithm:
  1. Find recent local extrema in both price and indicator (find_peaks).
  2. Check the last two extrema for divergence pattern.
  3. Confirm: divergence completed at current bar (no future info needed).

Confidence scales with divergence magnitude.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from ..base import PatternDetector, PatternSignal


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0).rolling(period, min_periods=period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(period, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    sig = macd.ewm(span=signal, adjust=False).mean()
    hist = macd - sig
    return macd, sig, hist


def _two_extrema_diverge_bull(price: np.ndarray, ind: np.ndarray, distance: int) -> tuple[int, int] | None:
    """Find lowest two troughs in price; verify indicator has higher trough at the SECOND.

    Returns (idx_first_trough, idx_second_trough) if bullish divergence holds.
    """
    troughs, _ = find_peaks(-price, distance=distance)
    if len(troughs) < 2:
        return None
    t1, t2 = troughs[-2], troughs[-1]
    if price[t2] < price[t1] and ind[t2] > ind[t1]:
        return (t1, t2)
    return None


def _two_extrema_diverge_bear(price: np.ndarray, ind: np.ndarray, distance: int):
    peaks, _ = find_peaks(price, distance=distance)
    if len(peaks) < 2:
        return None
    p1, p2 = peaks[-2], peaks[-1]
    if price[p2] > price[p1] and ind[p2] < ind[p1]:
        return (p1, p2)
    return None


class _DivergenceBase(PatternDetector):
    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "lookback": 50,
            "peak_distance": 5,
            "recency_window": 5,   # last extremum must be in the last N bars
            "cooldown_bars": 10,
            "horizon_bars": 10,
        }


class RSIBullishDivergence(_DivergenceBase):
    name = "rsi_bullish_divergence"
    category = "indicator"
    min_bars = 60

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        rsi = _rsi(df["close"], 14).fillna(50.0)
        signals: list[PatternSignal] = []
        lb = int(self.params["lookback"])
        recency = int(self.params["recency_window"])
        cooldown = int(self.params["cooldown_bars"])
        last_emit = -10**9
        for i in range(lb, len(df)):
            if i - last_emit < cooldown:
                continue
            window_close = df["close"].iloc[i - lb : i + 1].to_numpy()
            window_rsi = rsi.iloc[i - lb : i + 1].to_numpy()
            res = _two_extrema_diverge_bull(window_close, window_rsi, int(self.params["peak_distance"]))
            if res is None:
                continue
            t1, t2 = res
            # second trough must be in the recent window (not boundary-strict)
            if t2 < lb - recency:
                continue
            ts = df.index[i]
            close = float(df["close"].iloc[i])
            low = float(df["low"].iloc[i])
            price_drop = (window_close[t1] - window_close[t2]) / window_close[t1]
            rsi_rise = (window_rsi[t2] - window_rsi[t1]) / 50.0
            base = 0.45 + 0.30 * min(1.0, price_drop / 0.10) + 0.25 * min(1.0, abs(rsi_rise) / 0.4)
            base = max(0.0, min(1.0, base))
            last_emit = i
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bull",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=None,
                    suggested_stop=low,
                    metadata={"price_drop_pct": float(price_drop), "rsi_t1": float(window_rsi[t1]), "rsi_t2": float(window_rsi[t2])},
                )
            )
        return signals


class RSIBearishDivergence(_DivergenceBase):
    name = "rsi_bearish_divergence"
    category = "indicator"
    min_bars = 60

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        rsi = _rsi(df["close"], 14).fillna(50.0)
        signals: list[PatternSignal] = []
        lb = int(self.params["lookback"])
        recency = int(self.params["recency_window"])
        cooldown = int(self.params["cooldown_bars"])
        last_emit = -10**9
        for i in range(lb, len(df)):
            if i - last_emit < cooldown:
                continue
            window_close = df["close"].iloc[i - lb : i + 1].to_numpy()
            window_rsi = rsi.iloc[i - lb : i + 1].to_numpy()
            res = _two_extrema_diverge_bear(window_close, window_rsi, int(self.params["peak_distance"]))
            if res is None:
                continue
            p1, p2 = res
            if p2 < lb - recency:
                continue
            ts = df.index[i]
            close = float(df["close"].iloc[i])
            high = float(df["high"].iloc[i])
            price_rise = (window_close[p2] - window_close[p1]) / window_close[p1]
            rsi_drop = (window_rsi[p1] - window_rsi[p2]) / 50.0
            base = 0.45 + 0.30 * min(1.0, price_rise / 0.10) + 0.25 * min(1.0, abs(rsi_drop) / 0.4)
            base = max(0.0, min(1.0, base))
            last_emit = i
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bear",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=None,
                    suggested_stop=high,
                    metadata={"price_rise_pct": float(price_rise)},
                )
            )
        return signals


class MACDBullishDivergence(_DivergenceBase):
    name = "macd_bullish_divergence"
    category = "indicator"
    min_bars = 80

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        macd, _, _ = _macd(df["close"])
        macd = macd.fillna(0.0)
        signals: list[PatternSignal] = []
        lb = int(self.params["lookback"])
        recency = int(self.params["recency_window"])
        cooldown = int(self.params["cooldown_bars"])
        last_emit = -10**9
        for i in range(lb, len(df)):
            if i - last_emit < cooldown:
                continue
            wc = df["close"].iloc[i - lb : i + 1].to_numpy()
            wm = macd.iloc[i - lb : i + 1].to_numpy()
            res = _two_extrema_diverge_bull(wc, wm, int(self.params["peak_distance"]))
            if res is None:
                continue
            t1, t2 = res
            if t2 < lb - recency:
                continue
            ts = df.index[i]
            low = float(df["low"].iloc[i])
            price_drop = (wc[t1] - wc[t2]) / wc[t1]
            base = 0.45 + 0.35 * min(1.0, price_drop / 0.10) + 0.20
            base = max(0.0, min(1.0, base))
            last_emit = i
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bull",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=None,
                    suggested_stop=low,
                    metadata={"price_drop_pct": float(price_drop)},
                )
            )
        return signals


class MACDBearishDivergence(_DivergenceBase):
    name = "macd_bearish_divergence"
    category = "indicator"
    min_bars = 80

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        macd, _, _ = _macd(df["close"])
        macd = macd.fillna(0.0)
        signals: list[PatternSignal] = []
        lb = int(self.params["lookback"])
        recency = int(self.params["recency_window"])
        cooldown = int(self.params["cooldown_bars"])
        last_emit = -10**9
        for i in range(lb, len(df)):
            if i - last_emit < cooldown:
                continue
            wc = df["close"].iloc[i - lb : i + 1].to_numpy()
            wm = macd.iloc[i - lb : i + 1].to_numpy()
            res = _two_extrema_diverge_bear(wc, wm, int(self.params["peak_distance"]))
            if res is None:
                continue
            p1, p2 = res
            if p2 < lb - recency:
                continue
            ts = df.index[i]
            high = float(df["high"].iloc[i])
            price_rise = (wc[p2] - wc[p1]) / wc[p1]
            base = 0.45 + 0.35 * min(1.0, price_rise / 0.10) + 0.20
            base = max(0.0, min(1.0, base))
            last_emit = i
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bear",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=None,
                    suggested_stop=high,
                    metadata={"price_rise_pct": float(price_rise)},
                )
            )
        return signals
