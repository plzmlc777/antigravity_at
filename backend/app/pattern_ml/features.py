"""Feature engineering — turn (pattern signals + regime + OHLCV) into a
feature matrix indexed by evaluation timestamps.

Each row = one evaluation moment. Columns:

  Pattern aggregates (count of FDR-active signals in lookback window):
    pat_chart_bull_4h_lookN, pat_chart_bear_4h_lookN, ...
    pat_candle_bull_15m_lookN, ...

  Pattern confidence sums (sum of confidence × edge_mean):
    pat_chart_score_4h_lookN, ...

  Regime continuous scores (forward-filled to evaluation freq):
    trend_score_1d, vol_score_1d, liq_score_1d, mom_score_1d

  Market state:
    ret_1, ret_5, ret_20 (log returns)
    vol_realized_5, vol_realized_20 (rolling stdev)
    vol_z (volume z-score)

  Calendar:
    dow (0-6)

Target (separate column, not feature):
    fwd_ret_N (log return over next N bars at eval_freq)
"""
from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


def _safe_log_ret(x: pd.Series, lag: int) -> pd.Series:
    return np.log(x / x.shift(lag))


def build_feature_matrix(
    *,
    ohlcv_eval: pd.DataFrame,           # OHLCV at the evaluation timeframe (e.g., 1d)
    signals_df: pd.DataFrame,           # full pattern signal tensor (all TFs)
    regime_eval: pd.DataFrame,          # regime DF at eval timeframe
    eval_freq_minutes: int,             # for fwd return horizon math
    forward_bars: int = 5,              # N bars forward for target
    pattern_lookback_bars: int = 5,     # how many recent bars to aggregate signals over
) -> pd.DataFrame:
    """Return a DataFrame indexed by ohlcv_eval.index containing all features
    plus target column `target_fwd_ret`."""
    if not isinstance(ohlcv_eval.index, pd.DatetimeIndex):
        raise ValueError("ohlcv_eval must have DatetimeIndex")

    out = pd.DataFrame(index=ohlcv_eval.index)
    close = ohlcv_eval["close"].astype(float)

    # --- market state
    out["ret_1"] = _safe_log_ret(close, 1)
    out["ret_5"] = _safe_log_ret(close, 5)
    out["ret_20"] = _safe_log_ret(close, 20)
    out["vol_realized_5"] = out["ret_1"].rolling(5).std(ddof=0)
    out["vol_realized_20"] = out["ret_1"].rolling(20).std(ddof=0)
    if "volume" in ohlcv_eval.columns:
        v = ohlcv_eval["volume"].astype(float)
        v_mean = v.rolling(20).mean()
        v_std = v.rolling(20).std(ddof=0)
        out["vol_z"] = (v - v_mean) / v_std.replace(0, np.nan)
    else:
        out["vol_z"] = 0.0

    # --- calendar
    out["dow"] = out.index.dayofweek

    # --- regime continuous scores
    if len(regime_eval) > 0:
        reg = regime_eval.copy()
        reg.index = pd.to_datetime(reg.index)
        # forward-fill to eval index
        re = reg.reindex(out.index, method="ffill")
        for col in ("trend_score", "volatility_score", "liquidity_score", "momentum_score"):
            if col in re.columns:
                out[col] = pd.to_numeric(re[col], errors="coerce")
            else:
                out[col] = 0.0
    else:
        for col in ("trend_score", "volatility_score", "liquidity_score", "momentum_score"):
            out[col] = 0.0

    # --- pattern aggregates
    # We map each signal's emit time onto the eval index by floor(.) and count
    # signals within the last `pattern_lookback_bars` eval bars.
    sig = signals_df.copy()
    if len(sig):
        sig["timestamp"] = pd.to_datetime(sig["timestamp"])

        # category × direction aggregation (12 buckets × pattern_lookback_bars)
        from app.patterns import PatternRegistry
        PatternRegistry.discover()
        cat_lookup: dict[str, str] = {}
        for det in PatternRegistry.all():
            cat_lookup[det.name] = det.category
        sig["category"] = sig["pattern_name"].map(cat_lookup).fillna("chart")

        # Floor signal timestamps to eval bar
        eval_freq_str = f"{eval_freq_minutes}min" if eval_freq_minutes < 1440 else "1D"
        sig["eval_bar"] = sig["timestamp"].dt.floor(eval_freq_str if eval_freq_minutes < 1440 else "D")

        # Per (category, direction) groupby → per-bar counts
        for cat in ("chart", "candle", "indicator", "volume"):
            for dirn in ("bull", "bear", "neutral"):
                col = f"pat_{cat}_{dirn}_count"
                mask = (sig["category"] == cat) & (sig["direction"] == dirn)
                bar_counts = sig.loc[mask].groupby("eval_bar").size()
                # forward-fill onto out.index
                series = bar_counts.reindex(out.index, fill_value=0)
                # rolling sum over lookback window
                out[col] = series.rolling(pattern_lookback_bars, min_periods=1).sum()

        # Total confidence sum per direction (intensity proxy)
        for dirn in ("bull", "bear"):
            col = f"pat_conf_sum_{dirn}"
            mask = sig["direction"] == dirn
            conf_by_bar = sig.loc[mask].groupby("eval_bar")["confidence"].sum()
            series = conf_by_bar.reindex(out.index, fill_value=0.0)
            out[col] = series.rolling(pattern_lookback_bars, min_periods=1).sum()
    else:
        # no signals
        for cat in ("chart", "candle", "indicator", "volume"):
            for dirn in ("bull", "bear", "neutral"):
                out[f"pat_{cat}_{dirn}_count"] = 0
        out["pat_conf_sum_bull"] = 0.0
        out["pat_conf_sum_bear"] = 0.0

    # --- target: forward N-bar log return (look-ahead safe — won't be available
    # at inference time; used only for training)
    out["target_fwd_ret"] = np.log(close.shift(-forward_bars) / close)

    return out


def feature_columns(df: pd.DataFrame) -> list[str]:
    """Stable list of feature columns (excluding target)."""
    return [c for c in df.columns if c != "target_fwd_ret"]
