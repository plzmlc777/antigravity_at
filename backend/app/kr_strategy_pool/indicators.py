"""기본 기술지표 — pandas로 직접 구현(외부 의존성 없음)."""
from typing import Tuple

import numpy as np
import pandas as pd


def rsi(closes: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI (EWM 알파=1/period)."""
    delta = closes.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def bollinger(
    closes: pd.Series, period: int = 20, std_n: float = 2.0
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Returns (upper, mid, lower)."""
    mid = closes.rolling(period).mean()
    std = closes.rolling(period).std(ddof=0)
    return mid + std_n * std, mid, mid - std_n * std


def vwap_intraday(
    high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, day_id: pd.Series
) -> pd.Series:
    """일중 VWAP — day_id별로 cumsum 리셋."""
    typical = (high + low + close) / 3.0
    pv = typical * volume
    cum_pv = pv.groupby(day_id).cumsum()
    cum_v = volume.groupby(day_id).cumsum()
    return cum_pv / cum_v.replace(0, np.nan)


def rolling_std(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).std(ddof=0)


def donchian(
    high: pd.Series, low: pd.Series, period: int = 20
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Donchian channel: (upper, mid, lower) — past 'period' bars excluding current."""
    upper = high.shift(1).rolling(period).max()
    lower = low.shift(1).rolling(period).min()
    mid = (upper + lower) / 2.0
    return upper, mid, lower


def macd(
    closes: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Returns (macd_line, signal_line, histogram)."""
    ema_fast = closes.ewm(span=fast, adjust=False).mean()
    ema_slow = closes.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist
