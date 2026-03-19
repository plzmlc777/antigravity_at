"""
Feature Engineering for ML Trend Prediction.
Generates technical indicator + on-chain features from OHLCV + funding + OI data.
"""
import numpy as np
import pandas as pd


def compute_features(df: pd.DataFrame, funding_df: pd.DataFrame = None,
                     oi_df: pd.DataFrame = None) -> pd.DataFrame:
    df = df.copy()
    df.sort_values('timestamp', inplace=True)
    df.reset_index(drop=True, inplace=True)

    c = df['close']
    h = df['high']
    l = df['low']
    o = df['open']
    v = df['volume'].astype(float)

    # ========== Price Returns ==========
    for period in [1, 3, 6, 12, 24, 48]:
        df[f'ret_{period}'] = c.pct_change(period)

    # ========== Moving Averages & Crossovers ==========
    for span in [9, 21, 50, 100, 200]:
        ema = c.ewm(span=span, adjust=False).mean()
        df[f'ema_{span}_dist'] = (c - ema) / ema

    ema9 = c.ewm(span=9, adjust=False).mean()
    ema21 = c.ewm(span=21, adjust=False).mean()
    ema50 = c.ewm(span=50, adjust=False).mean()
    ema200 = c.ewm(span=200, adjust=False).mean()
    df['ema_cross_9_21'] = ema9 - ema21
    df['ema_cross_21_50'] = ema21 - ema50
    df['ema_cross_50_200'] = ema50 - ema200

    # ========== RSI ==========
    for period in [7, 14, 21]:
        delta = c.diff()
        gain = delta.where(delta > 0, 0.0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
        rs = gain / loss.replace(0, np.nan)
        df[f'rsi_{period}'] = 100 - (100 / (1 + rs))

    # Stochastic RSI (14-period)
    rsi_14 = df['rsi_14']
    rsi_min = rsi_14.rolling(14).min()
    rsi_max = rsi_14.rolling(14).max()
    rsi_range = (rsi_max - rsi_min).replace(0, np.nan)
    df['stoch_rsi'] = (rsi_14 - rsi_min) / rsi_range
    df['stoch_rsi_k'] = df['stoch_rsi'].rolling(3).mean()
    df['stoch_rsi_d'] = df['stoch_rsi_k'].rolling(3).mean()

    # ========== MACD ==========
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    df['macd_hist_diff'] = df['macd_hist'].diff()

    # ========== Bollinger Bands ==========
    for period in [20, 50]:
        bb_ma = c.rolling(period).mean()
        bb_std = c.rolling(period).std()
        bb_upper = bb_ma + 2 * bb_std
        bb_lower = bb_ma - 2 * bb_std
        df[f'bb_width_{period}'] = (bb_upper - bb_lower) / bb_ma
        df[f'bb_pct_{period}'] = (c - bb_lower) / (bb_upper - bb_lower).replace(0, np.nan)

    # ========== ATR ==========
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    for period in [7, 14, 21]:
        df[f'atr_pct_{period}'] = tr.rolling(period).mean() / c

    # ========== ADX ==========
    plus_dm = h.diff().where(lambda x: (x > 0) & (x > -l.diff()), 0.0)
    minus_dm = (-l.diff()).where(lambda x: (x > 0) & (x > h.diff()), 0.0)
    atr_smooth = tr.rolling(14).mean().replace(0, np.nan)
    plus_di = 100 * (plus_dm.rolling(14).mean() / atr_smooth)
    minus_di = 100 * (minus_dm.rolling(14).mean() / atr_smooth)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    df['adx'] = dx.rolling(14).mean()
    df['plus_di'] = plus_di
    df['minus_di'] = minus_di
    df['di_diff'] = plus_di - minus_di

    # ========== Williams %R ==========
    for period in [14, 24]:
        hh = h.rolling(period).max()
        ll = l.rolling(period).min()
        df[f'williams_r_{period}'] = (hh - c) / (hh - ll).replace(0, np.nan) * -100

    # ========== CCI (Commodity Channel Index) ==========
    for period in [14, 20]:
        tp = (h + l + c) / 3
        tp_ma = tp.rolling(period).mean()
        tp_md = tp.rolling(period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
        df[f'cci_{period}'] = (tp - tp_ma) / (0.015 * tp_md.replace(0, np.nan))

    # ========== MFI (Money Flow Index) ==========
    tp = (h + l + c) / 3
    mf = tp * v
    tp_diff = tp.diff()
    pos_mf = mf.where(tp_diff > 0, 0.0).rolling(14).sum()
    neg_mf = mf.where(tp_diff <= 0, 0.0).rolling(14).sum()
    mfr = pos_mf / neg_mf.replace(0, np.nan)
    df['mfi_14'] = 100 - (100 / (1 + mfr))

    # ========== Volume ==========
    vol_ma20 = v.rolling(20).mean().replace(0, np.nan)
    vol_ma50 = v.rolling(50).mean().replace(0, np.nan)
    df['vol_ratio_20'] = v / vol_ma20
    df['vol_ratio_50'] = v / vol_ma50
    df['vol_trend'] = vol_ma20 / vol_ma50
    obv = (np.sign(c.diff()) * v).cumsum()
    df['obv_change_5'] = obv.pct_change(5)
    df['obv_change_12'] = obv.pct_change(12)
    # Volume-price divergence
    df['vol_price_corr'] = c.pct_change().rolling(24).corr(v.pct_change())

    # ========== Candle Patterns ==========
    body = (c - o).abs()
    total_range = (h - l).replace(0, np.nan)
    df['body_ratio'] = body / total_range
    df['upper_shadow'] = (h - pd.concat([c, o], axis=1).max(axis=1)) / total_range
    df['lower_shadow'] = (pd.concat([c, o], axis=1).min(axis=1) - l) / total_range
    df['candle_dir'] = np.sign(c - o)  # 1=bullish, -1=bearish
    # Consecutive candle direction
    df['consec_dir'] = df['candle_dir'].rolling(5).sum()

    # ========== Price Position ==========
    for period in [24, 48, 96, 168]:
        rh = h.rolling(period).max()
        rl = l.rolling(period).min()
        df[f'price_pos_{period}'] = (c - rl) / (rh - rl).replace(0, np.nan)

    # ========== Volatility ==========
    for period in [12, 24, 48, 96]:
        df[f'volatility_{period}'] = c.pct_change().rolling(period).std()
    # Volatility ratio (short/long)
    df['vol_ratio_12_48'] = df['volatility_12'] / df['volatility_48'].replace(0, np.nan)

    # ========== Momentum ==========
    for period in [6, 12, 24, 48]:
        df[f'roc_{period}'] = (c / c.shift(period) - 1) * 100

    # ========== Squeeze / Pre-Explosion Detection ==========
    # Bollinger Band squeeze: width shrinking = volatility compression
    bb_w20 = df['bb_width_20']
    df['bb_squeeze_20'] = bb_w20 / bb_w20.rolling(48).mean().replace(0, np.nan)  # <1 = squeezing
    df['bb_squeeze_50'] = df['bb_width_50'] / df['bb_width_50'].rolling(96).mean().replace(0, np.nan)

    # BB width percentile over last 168h (1 week) — low percentile = rare squeeze
    df['bb_width_pctile'] = bb_w20.rolling(168).rank(pct=True)

    # ATR contraction: current ATR vs recent ATR — dropping ATR = calm before storm
    atr14 = df['atr_pct_14']
    df['atr_contraction'] = atr14 / atr14.rolling(48).mean().replace(0, np.nan)  # <1 = contracting
    df['atr_contraction_rate'] = atr14.pct_change(12)  # negative = ATR dropping

    # Volatility regime: current vol vs longer-term vol
    df['vol_regime'] = df['volatility_12'] / df['volatility_96'].replace(0, np.nan)  # <1 = quiet

    # Volume dry-up then spike pattern
    vol_ma5 = v.rolling(5).mean()
    vol_ma20_local = v.rolling(20).mean().replace(0, np.nan)
    df['vol_dryup'] = vol_ma5 / vol_ma20_local  # <1 = volume drying up
    df['vol_spike_1'] = v / vol_ma20_local  # current bar vs 20-period avg

    # Price range compression: high-low range shrinking
    range_pct = (h - l) / c
    df['range_compression'] = range_pct.rolling(6).mean() / range_pct.rolling(48).mean().replace(0, np.nan)

    # Consecutive narrow-range bars (inside bars pattern)
    avg_range = range_pct.rolling(20).mean()
    narrow = (range_pct < avg_range * 0.7).astype(float)
    df['narrow_range_count'] = narrow.rolling(6).sum()  # how many of last 6 bars are narrow

    # OI buildup without price move = tension building
    if 'oi' in df.columns:
        oi_chg = df['oi'].pct_change(12)
        price_chg = c.pct_change(12).abs()
        df['oi_price_diverge'] = oi_chg / price_chg.replace(0, np.nan)  # high = OI up, price flat

    # Funding rate extreme (absolute) — extreme positioning = liquidation risk
    if 'funding_rate' in df.columns:
        df['funding_abs_zscore'] = (
            df['funding_rate'].abs() - df['funding_rate'].abs().rolling(72).mean()
        ) / df['funding_rate'].abs().rolling(72).std().replace(0, np.nan)

    # ADX trend strength declining = range-bound = potential breakout
    if 'adx' in df.columns:
        df['adx_declining'] = df['adx'].diff(6)  # negative = trend weakening → range
        df['adx_low'] = (df['adx'] < 20).astype(float)  # ADX < 20 = no trend

    # ========== Time Features ==========
    if 'timestamp' in df.columns:
        ts = pd.to_datetime(df['timestamp'])
        df['hour_sin'] = np.sin(2 * np.pi * ts.dt.hour / 24)
        df['hour_cos'] = np.cos(2 * np.pi * ts.dt.hour / 24)
        df['dow_sin'] = np.sin(2 * np.pi * ts.dt.dayofweek / 7)
        df['dow_cos'] = np.cos(2 * np.pi * ts.dt.dayofweek / 7)

    # ========== Funding Rate Features ==========
    if funding_df is not None and len(funding_df) > 0:
        fund = funding_df[['timestamp', 'funding_rate']].copy()
        fund.sort_values('timestamp', inplace=True)
        # Forward-fill funding rate to hourly (funding is every 8h)
        df = pd.merge_asof(
            df.sort_values('timestamp'),
            fund.sort_values('timestamp'),
            on='timestamp', direction='backward')
        df['funding_rate'] = df['funding_rate'].fillna(0)
        df['funding_ma_8'] = df['funding_rate'].rolling(8, min_periods=1).mean()
        df['funding_ma_24'] = df['funding_rate'].rolling(24, min_periods=1).mean()
        df['funding_extreme'] = df['funding_rate'].abs()
    else:
        df['funding_rate'] = 0.0
        df['funding_ma_8'] = 0.0
        df['funding_ma_24'] = 0.0
        df['funding_extreme'] = 0.0

    # ========== Open Interest Features ==========
    if oi_df is not None and len(oi_df) > 0:
        oi = oi_df[['timestamp', 'open_interest', 'open_interest_value']].copy()
        oi.sort_values('timestamp', inplace=True)
        df = pd.merge_asof(
            df.sort_values('timestamp'),
            oi.sort_values('timestamp'),
            on='timestamp', direction='backward')
        df['oi'] = df['open_interest'].fillna(method='ffill')
        df['oi_value'] = df['open_interest_value'].fillna(method='ffill')
        oi_series = df['oi']
        df['oi_change_1'] = oi_series.pct_change(1)
        df['oi_change_6'] = oi_series.pct_change(6)
        df['oi_change_24'] = oi_series.pct_change(24)
        df['oi_ma_ratio'] = oi_series / oi_series.rolling(24, min_periods=1).mean()
        # OI-Price divergence
        df['oi_price_corr'] = c.pct_change().rolling(24).corr(oi_series.pct_change())
        df.drop(columns=['open_interest', 'open_interest_value'], inplace=True, errors='ignore')
    else:
        for col in ['oi', 'oi_value', 'oi_change_1', 'oi_change_6',
                     'oi_change_24', 'oi_ma_ratio', 'oi_price_corr']:
            df[col] = 0.0

    df.sort_values('timestamp', inplace=True)
    df.reset_index(drop=True, inplace=True)
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


def add_volatility_target(df: pd.DataFrame, horizon: int = 12,
                          threshold: float = 0.015) -> pd.DataFrame:
    """BIG_MOVE=1 if |future_return| > threshold, else SMALL_MOVE=0."""
    df = df.copy()
    future_return = df['close'].shift(-horizon) / df['close'] - 1
    df['target'] = (future_return.abs() > threshold).astype(int)
    return df


def add_direction_target(df: pd.DataFrame, horizon: int = 12) -> pd.DataFrame:
    """UP=1 if future_return > 0, DOWN=0. Only for BIG_MOVE filtered data."""
    df = df.copy()
    future_return = df['close'].shift(-horizon) / df['close'] - 1
    df['target'] = (future_return > 0).astype(int)
    return df
