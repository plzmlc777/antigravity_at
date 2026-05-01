"""기술 지표 — kr_strategy_pool.indicators의 동일 구현 (시장 무관).

re-export 대신 복사하여 패키지 자기완결성 유지. 추후 두 패키지가 따로 진화하더라도
독립적으로 변경 가능.
"""
from typing import Tuple

import numpy as np
import pandas as pd


def rsi(closes: pd.Series, period: int = 14) -> pd.Series:
    delta = closes.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def bollinger(closes: pd.Series, period: int = 20, std_n: float = 2.0):
    mid = closes.rolling(period).mean()
    std = closes.rolling(period).std(ddof=0)
    return mid + std_n * std, mid, mid - std_n * std


def vwap_intraday(high, low, close, volume, day_id) -> pd.Series:
    typical = (high + low + close) / 3.0
    pv = typical * volume
    cum_pv = pv.groupby(day_id).cumsum()
    cum_v = volume.groupby(day_id).cumsum()
    return cum_pv / cum_v.replace(0, np.nan)


def rolling_std(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).std(ddof=0)


def donchian(high: pd.Series, low: pd.Series, period: int = 20):
    upper = high.shift(1).rolling(period).max()
    lower = low.shift(1).rolling(period).min()
    mid = (upper + lower) / 2.0
    return upper, mid, lower


def macd(closes: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = closes.ewm(span=fast, adjust=False).mean()
    ema_slow = closes.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line, macd_line - signal_line


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def atr(high, low, close, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    sign = (close.diff().fillna(0) > 0).astype(int) - (close.diff().fillna(0) < 0).astype(int)
    return (sign * volume).cumsum()


def supertrend(high, low, close, period: int = 10, multiplier: float = 3.0):
    a = atr(high, low, close, period)
    hl2 = (high + low) / 2.0
    upper = hl2 + multiplier * a
    lower = hl2 - multiplier * a

    st = pd.Series(index=close.index, dtype=float)
    direction = pd.Series(index=close.index, dtype=int)

    for i in range(len(close)):
        if i == 0:
            st.iat[i] = upper.iat[i]
            direction.iat[i] = -1
            continue
        prev_st = st.iat[i - 1]
        prev_dir = direction.iat[i - 1]
        c = close.iat[i]
        if prev_dir == 1:
            cur = max(lower.iat[i], prev_st)
            if c <= cur:
                cur = upper.iat[i]
                cur_dir = -1
            else:
                cur_dir = 1
        else:
            cur = min(upper.iat[i], prev_st)
            if c >= cur:
                cur = lower.iat[i]
                cur_dir = 1
            else:
                cur_dir = -1
        st.iat[i] = cur
        direction.iat[i] = cur_dir
    return st, direction


def keltner(high, low, close, ema_period: int = 20, atr_period: int = 10, multiplier: float = 2.0):
    mid = ema(close, ema_period)
    a = atr(high, low, close, atr_period)
    return mid + multiplier * a, mid, mid - multiplier * a


def stochastic(high, low, close, k_period: int = 14, d_period: int = 3):
    lowest_low = low.rolling(k_period).min()
    highest_high = high.rolling(k_period).max()
    k = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)
    d = k.rolling(d_period).mean()
    return k, d


def williams_r(high, low, close, period: int = 14) -> pd.Series:
    highest_high = high.rolling(period).max()
    lowest_low = low.rolling(period).min()
    return -100 * (highest_high - close) / (highest_high - lowest_low).replace(0, np.nan)


def zscore(series: pd.Series, period: int = 20) -> pd.Series:
    m = series.rolling(period).mean()
    s = series.rolling(period).std(ddof=0)
    return (series - m) / s.replace(0, np.nan)


def adx(high, low, close, period: int = 14) -> pd.Series:
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = ((up_move > down_move) & (up_move > 0)).astype(float) * up_move
    minus_dm = ((down_move > up_move) & (down_move > 0)).astype(float) * down_move
    a = atr(high, low, close, period)
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / a.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / a.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False).mean()


def mfi(high, low, close, volume, period: int = 14) -> pd.Series:
    typical = (high + low + close) / 3.0
    raw_mf = typical * volume
    delta = typical.diff()
    pos_mf = raw_mf.where(delta > 0, 0).rolling(period).sum()
    neg_mf = raw_mf.where(delta < 0, 0).rolling(period).sum()
    mfr = pos_mf / neg_mf.replace(0, np.nan)
    return 100 - 100 / (1 + mfr)


def ichimoku(high, low, close, tenkan: int = 9, kijun: int = 26, senkou_b: int = 52):
    conv = (high.rolling(tenkan).max() + low.rolling(tenkan).min()) / 2.0
    base = (high.rolling(kijun).max() + low.rolling(kijun).min()) / 2.0
    span_a = (conv + base) / 2.0
    span_b = (high.rolling(senkou_b).max() + low.rolling(senkou_b).min()) / 2.0
    return conv, base, span_a, span_b


def natr(high, low, close, period: int = 14) -> pd.Series:
    return atr(high, low, close, period) / close.replace(0, np.nan) * 100
