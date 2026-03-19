"""
Feature Engineering for ML Trend Prediction.
Generates technical indicator features from OHLCV data.
"""
import numpy as np
import pandas as pd


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.sort_values('timestamp', inplace=True)
    df.reset_index(drop=True, inplace=True)

    c = df['close']
    h = df['high']
    l = df['low']
    o = df['open']
    v = df['volume'].astype(float)

    # Price Returns
    for period in [1, 3, 6, 12, 24, 48]:
        df[f'ret_{period}'] = c.pct_change(period)

    # Moving Averages & Crossovers
    for span in [9, 21, 50, 100]:
        ema = c.ewm(span=span, adjust=False).mean()
        df[f'ema_{span}_dist'] = (c - ema) / ema

    ema9 = c.ewm(span=9, adjust=False).mean()
    ema21 = c.ewm(span=21, adjust=False).mean()
    ema50 = c.ewm(span=50, adjust=False).mean()
    df['ema_cross_9_21'] = ema9 - ema21
    df['ema_cross_21_50'] = ema21 - ema50

    # RSI
    for period in [14, 21]:
        delta = c.diff()
        gain = delta.where(delta > 0, 0.0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
        rs = gain / loss.replace(0, np.nan)
        df[f'rsi_{period}'] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']

    # Bollinger Bands
    bb_ma = c.rolling(20).mean()
    bb_std = c.rolling(20).std()
    bb_upper = bb_ma + 2 * bb_std
    bb_lower = bb_ma - 2 * bb_std
    df['bb_width'] = (bb_upper - bb_lower) / bb_ma
    df['bb_pct'] = (c - bb_lower) / (bb_upper - bb_lower).replace(0, np.nan)

    # ATR
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    df['atr_pct'] = tr.rolling(14).mean() / c

    # ADX
    plus_dm = h.diff().where(lambda x: (x > 0) & (x > -l.diff()), 0.0)
    minus_dm = (-l.diff()).where(lambda x: (x > 0) & (x > h.diff()), 0.0)
    atr_smooth = tr.rolling(14).mean().replace(0, np.nan)
    plus_di = 100 * (plus_dm.rolling(14).mean() / atr_smooth)
    minus_di = 100 * (minus_dm.rolling(14).mean() / atr_smooth)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    df['adx'] = dx.rolling(14).mean()
    df['plus_di'] = plus_di
    df['minus_di'] = minus_di

    # Volume
    vol_ma = v.rolling(20).mean().replace(0, np.nan)
    df['vol_ratio'] = v / vol_ma
    obv = (np.sign(c.diff()) * v).cumsum()
    df['obv_change'] = obv.pct_change(5)

    # Candle Patterns
    body = (c - o).abs()
    total_range = (h - l).replace(0, np.nan)
    df['body_ratio'] = body / total_range
    df['upper_shadow'] = (h - pd.concat([c, o], axis=1).max(axis=1)) / total_range
    df['lower_shadow'] = (pd.concat([c, o], axis=1).min(axis=1) - l) / total_range

    # Price Position
    for period in [24, 48, 96]:
        rh = h.rolling(period).max()
        rl = l.rolling(period).min()
        df[f'price_pos_{period}'] = (c - rl) / (rh - rl).replace(0, np.nan)

    # Volatility
    df['volatility_24'] = c.pct_change().rolling(24).std()
    df['volatility_48'] = c.pct_change().rolling(48).std()

    # Momentum
    df['roc_12'] = (c / c.shift(12) - 1) * 100
    df['roc_24'] = (c / c.shift(24) - 1) * 100

    return df


def get_feature_columns(df: pd.DataFrame) -> list:
    exclude = {'open', 'high', 'low', 'close', 'volume', 'timestamp',
               'symbol', 'time_frame', 'id', 'created_at', 'target'}
    return [c for c in df.columns if c not in exclude and not df[c].isna().all()]


def add_target(df: pd.DataFrame, horizon: int = 12, threshold: float = 0.0) -> pd.DataFrame:
    df = df.copy()
    future_return = df['close'].shift(-horizon) / df['close'] - 1
    df['target'] = (future_return > threshold).astype(int)
    return df
