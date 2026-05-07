"""BinanceSmartMoneySource — strong cumulative positioning features from
5-minute Binance metrics archive (toptrader L/S ratio, global account L/S ratio).

Difference from BinanceMicrostructureSource (existing):
  - Existing source builds simple per-bar mean/zscore_20 features → LGBM
    consistently rated them at ~0% feature importance in prior OOS runs.
  - This source mirrors the KR Flow pattern: explicit 5d / 20d CUMULATIVE
    deviations from balance, 60d z-scores, smart-vs-dumb divergence
    accumulation, and regime-shift indicators.

Hypothesis: positioning extremes detected as multi-day accumulations carry
KR-Flow-like decisive signal that single-day means don't.

Output (all prefixed `sm_`):
  sm_top_pos_mean_1d           — daily mean of toptrader_position_ls_ratio
  sm_top_pos_dev_1d            — deviation from 1.0 (1.0 = balanced)
  sm_top_pos_5d_cum_dev        — sum of (mean-1.0) over last 5 days
  sm_top_pos_20d_cum_dev       — sum over 20 days
  sm_top_pos_zscore_60d        — 60d z-score of daily mean
  sm_top_pos_change_1d         — day-over-day delta
  sm_top_pos_change_5d_cum     — 5d cumulative delta (shift momentum)
  sm_global_acc_mean_1d, sm_global_acc_dev_1d, sm_global_acc_5d_cum_dev
  sm_divergence                — top_pos − global_acc (smart vs dumb)
  sm_divergence_5d_cum         — 5d sum
  sm_divergence_zscore_60d
  sm_taker_buy_dom_1d          — fraction of 5-min bars with taker_ratio > 1.5
  sm_taker_sell_dom_1d         — fraction < 0.667
  sm_taker_imbalance_5d_cum    — 5d sum of (buy_dom - sell_dom)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext


def _daily_smart_money_features(metrics_5m: pd.DataFrame) -> pd.DataFrame:
    """Resample 5-min metrics to daily smart-money features (UTC-day)."""
    if metrics_5m is None or metrics_5m.empty:
        return pd.DataFrame()
    df = metrics_5m.copy()
    df = df.replace(0.0, np.nan)
    g = df.resample("1D", origin="start_day")

    out = pd.DataFrame(index=g["toptrader_position_ls_ratio"].mean().index)

    # Top trader position L/S ratio (smart money positioning)
    out["top_pos_mean_1d"] = g["toptrader_position_ls_ratio"].mean()
    out["top_pos_dev_1d"] = out["top_pos_mean_1d"] - 1.0  # >0 long-skewed
    out["top_pos_5d_cum_dev"] = out["top_pos_dev_1d"].rolling(5, min_periods=2).sum()
    out["top_pos_20d_cum_dev"] = out["top_pos_dev_1d"].rolling(20, min_periods=5).sum()

    rmean60 = out["top_pos_mean_1d"].rolling(60, min_periods=20).mean()
    rstd60 = out["top_pos_mean_1d"].rolling(60, min_periods=20).std()
    out["top_pos_zscore_60d"] = (out["top_pos_mean_1d"] - rmean60) / rstd60.replace(0, np.nan)

    out["top_pos_change_1d"] = out["top_pos_mean_1d"].diff()
    out["top_pos_change_5d_cum"] = out["top_pos_change_1d"].rolling(5, min_periods=2).sum()

    # Global account L/S ratio (retail positioning baseline)
    out["global_acc_mean_1d"] = g["global_account_ls_ratio"].mean()
    out["global_acc_dev_1d"] = out["global_acc_mean_1d"] - 1.0
    out["global_acc_5d_cum_dev"] = out["global_acc_dev_1d"].rolling(5, min_periods=2).sum()

    # Smart-vs-dumb divergence (KR Flow analogue: institutional vs retail)
    out["divergence"] = out["top_pos_mean_1d"] - out["global_acc_mean_1d"]
    out["divergence_5d_cum"] = out["divergence"].rolling(5, min_periods=2).sum()
    div_rmean = out["divergence"].rolling(60, min_periods=20).mean()
    div_rstd = out["divergence"].rolling(60, min_periods=20).std()
    out["divergence_zscore_60d"] = (out["divergence"] - div_rmean) / div_rstd.replace(0, np.nan)

    # Taker imbalance (intraday flow, daily fraction)
    taker = df["taker_buy_sell_ratio"]
    buy_dom_series = (taker > 1.5).resample("1D", origin="start_day").mean()
    sell_dom_series = (taker < 0.667).resample("1D", origin="start_day").mean()
    out["taker_buy_dom_1d"] = buy_dom_series
    out["taker_sell_dom_1d"] = sell_dom_series
    out["taker_imbalance_5d_cum"] = (buy_dom_series - sell_dom_series).rolling(5, min_periods=2).sum()

    return out


class BinanceSmartMoneySource(SignalSource):
    name = "smartmoney"
    feature_prefix = "sm_"
    requires = ("ohlcv_eval",)

    def __init__(self, metrics_5m: pd.DataFrame) -> None:
        self.metrics_5m = metrics_5m

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        if self.metrics_5m is None or len(self.metrics_5m) == 0:
            return pd.DataFrame(index=ctx.ohlcv_eval.index)

        daily = _daily_smart_money_features(self.metrics_5m)
        if daily.empty:
            return pd.DataFrame(index=ctx.ohlcv_eval.index)

        eval_idx = pd.to_datetime(ctx.ohlcv_eval.index)
        eval_norm = eval_idx.normalize()
        daily = daily[~daily.index.duplicated(keep="last")]
        mapped = daily.reindex(
            pd.DatetimeIndex(sorted(set(daily.index) | set(eval_norm)))
        ).ffill().reindex(eval_norm)
        mapped.index = eval_idx
        return self._prefixed(mapped)
