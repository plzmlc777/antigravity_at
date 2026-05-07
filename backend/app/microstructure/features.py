"""Engineer microstructure features at the evaluation timeframe.

Input: 5-min metrics DataFrame with columns:
    open_interest, open_interest_value_usdt,
    toptrader_account_ls_ratio, toptrader_position_ls_ratio,
    global_account_ls_ratio,
    taker_buy_sell_ratio

Output (per eval bar): a feature dict with summary stats for the bar's window.
The hypothesis is that POSITIONING extremes (rapid OI growth, lopsided L/S,
sustained taker imbalance) carry information beyond price patterns.

Features per eval bar:
  oi_mean, oi_change_pct (vs prior bar), oi_zscore (vs trailing 20-bar mean)
  ls_top_account_mean, ls_top_account_change
  ls_top_position_mean, ls_top_position_change
  ls_global_mean, ls_global_change
  taker_ratio_mean, taker_ratio_std (intra-bar volatility)
  taker_ratio_extreme_pos (fraction of 5-min bars with ratio > 1.5)
  taker_ratio_extreme_neg (fraction with ratio < 0.667)
  ls_divergence — top trader vs global (smart vs dumb money)
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def aggregate_to_eval_bars(
    metrics_5m: pd.DataFrame,
    eval_index: pd.DatetimeIndex,
    eval_freq_minutes: int,
) -> pd.DataFrame:
    """Resample 5-min metrics to eval frequency, computing per-bar summaries."""
    if metrics_5m.empty:
        return pd.DataFrame(index=eval_index)

    df = metrics_5m.copy()
    df = df.replace(0.0, np.nan)  # OI=0 are sentinel/missing

    if eval_freq_minutes >= 1440:
        rule = "1D"
    else:
        rule = f"{eval_freq_minutes}min"

    g = df.resample(rule, origin="start_day")

    out = pd.DataFrame(index=eval_index)
    out["oi_mean"] = g["open_interest"].mean().reindex(eval_index)
    out["oi_value_mean"] = g["open_interest_value_usdt"].mean().reindex(eval_index)
    out["ls_top_account_mean"] = g["toptrader_account_ls_ratio"].mean().reindex(eval_index)
    out["ls_top_position_mean"] = g["toptrader_position_ls_ratio"].mean().reindex(eval_index)
    out["ls_global_mean"] = g["global_account_ls_ratio"].mean().reindex(eval_index)
    out["taker_ratio_mean"] = g["taker_buy_sell_ratio"].mean().reindex(eval_index)
    out["taker_ratio_std"] = g["taker_buy_sell_ratio"].std(ddof=0).reindex(eval_index)
    out["taker_extreme_pos"] = (df["taker_buy_sell_ratio"] > 1.5).resample(rule, origin="start_day").mean().reindex(eval_index)
    out["taker_extreme_neg"] = (df["taker_buy_sell_ratio"] < 0.667).resample(rule, origin="start_day").mean().reindex(eval_index)

    # Bar-over-bar changes (look-ahead safe — these use prior bar)
    out["oi_change_pct"] = out["oi_mean"].pct_change()
    out["ls_top_account_change"] = out["ls_top_account_mean"].diff()
    out["ls_top_position_change"] = out["ls_top_position_mean"].diff()
    out["ls_global_change"] = out["ls_global_mean"].diff()
    out["taker_ratio_change"] = out["taker_ratio_mean"].diff()

    # Trailing z-score (20-bar)
    rolling_mean = out["oi_mean"].rolling(20, min_periods=5).mean()
    rolling_std = out["oi_mean"].rolling(20, min_periods=5).std(ddof=0)
    out["oi_zscore_20"] = (out["oi_mean"] - rolling_mean) / rolling_std.replace(0, np.nan)

    rolling_mean_t = out["taker_ratio_mean"].rolling(20, min_periods=5).mean()
    rolling_std_t = out["taker_ratio_mean"].rolling(20, min_periods=5).std(ddof=0)
    out["taker_zscore_20"] = (out["taker_ratio_mean"] - rolling_mean_t) / rolling_std_t.replace(0, np.nan)

    # Smart vs dumb money divergence: top trader vs global
    # If top traders are MORE long than global, that's smart-money long signal
    out["ls_smart_minus_dumb"] = out["ls_top_position_mean"] - out["ls_global_mean"]

    # Prefix all columns to avoid collision with pattern features
    out = out.add_prefix("micro_")
    return out


def attach_to_feature_matrix(
    feat: pd.DataFrame,
    metrics_5m: pd.DataFrame,
    eval_freq_minutes: int,
) -> pd.DataFrame:
    """Concatenate microstructure features to an existing feature matrix
    (from app.pattern_ml.features.build_feature_matrix)."""
    micro = aggregate_to_eval_bars(metrics_5m, feat.index, eval_freq_minutes)
    return pd.concat([feat, micro], axis=1)
