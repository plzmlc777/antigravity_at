"""BinanceTakerFlowSource — daily cumulative buy/sell taker pressure.

Hypothesis: KR Flow의 직접 analogue. taker_buy_sell_ratio = (taker buy vol)/(taker sell vol).
값 1.0 = 균형, >1.0 = 매수 우세, <1.0 = 매도 우세.

KR Flow는 institutional/foreign 외인 net buying을 누적 → trend signal.
Taker imbalance는 actual aggressor flow → 단기 net buying 누적.

Difference from SmartMoney source:
  - SmartMoney = positioning (top trader L/S ratio)
  - TakerFlow  = actual aggressor flow (who hits the bid/ask harder)

다른 정보 도메인이므로 결정적인 종목이 다를 수 있음.

Output (prefix `tf_`):
  tf_taker_mean_1d           — daily mean of taker_buy_sell_ratio
  tf_taker_dev_1d            — deviation from 1.0
  tf_taker_5d_cum_dev        — 5d cum sum (net buying pressure 누적)
  tf_taker_20d_cum_dev       — 20d cum sum
  tf_taker_zscore_60d
  tf_taker_change_1d
  tf_taker_change_5d_cum
  tf_taker_extreme_buy_freq  — daily fraction of 5min bars with ratio > 1.5
  tf_taker_extreme_sell_freq — daily fraction with ratio < 0.667
  tf_taker_imbalance_persistence — 5d cum (buy_freq − sell_freq)
  tf_taker_pos_streak        — consecutive days of ratio > 1.0 (capped at 10)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext


def _build_taker_daily(metrics_5m: pd.DataFrame) -> pd.DataFrame:
    if metrics_5m is None or metrics_5m.empty or "taker_buy_sell_ratio" not in metrics_5m.columns:
        return pd.DataFrame()
    df = metrics_5m.copy()
    df["taker_buy_sell_ratio"] = pd.to_numeric(df["taker_buy_sell_ratio"], errors="coerce")
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=["taker_buy_sell_ratio"])
    if df.empty:
        return pd.DataFrame()
    df["log_ratio"] = np.log(df["taker_buy_sell_ratio"].clip(lower=1e-6))

    g = df.resample("1D", origin="start_day")
    out = pd.DataFrame(index=g["taker_buy_sell_ratio"].mean().index)
    out["taker_mean_1d"] = g["log_ratio"].mean()  # log space symmetric
    out["taker_dev_1d"] = out["taker_mean_1d"]    # since log(1)=0
    out["taker_5d_cum_dev"] = out["taker_dev_1d"].rolling(5, min_periods=2).sum()
    out["taker_20d_cum_dev"] = out["taker_dev_1d"].rolling(20, min_periods=5).sum()
    rmean60 = out["taker_mean_1d"].rolling(60, min_periods=20).mean()
    rstd60 = out["taker_mean_1d"].rolling(60, min_periods=20).std()
    out["taker_zscore_60d"] = (out["taker_mean_1d"] - rmean60) / rstd60.replace(0, np.nan)
    out["taker_change_1d"] = out["taker_mean_1d"].diff()
    out["taker_change_5d_cum"] = out["taker_change_1d"].rolling(5, min_periods=2).sum()

    raw = df["taker_buy_sell_ratio"]
    buy_freq = (raw > 1.5).resample("1D", origin="start_day").mean()
    sell_freq = (raw < 0.667).resample("1D", origin="start_day").mean()
    out["taker_extreme_buy_freq"] = buy_freq
    out["taker_extreme_sell_freq"] = sell_freq
    out["taker_imbalance_persistence"] = (buy_freq - sell_freq).rolling(5, min_periods=2).sum()

    pos_day = (out["taker_mean_1d"] > 0).astype(int)
    streak = pos_day.copy()
    for i in range(1, len(streak)):
        if pos_day.iloc[i] == 1 and pos_day.iloc[i - 1] == 1:
            streak.iloc[i] = streak.iloc[i - 1] + 1
        elif pos_day.iloc[i] == 0 and pos_day.iloc[i - 1] == 0:
            streak.iloc[i] = streak.iloc[i - 1] - 1
    out["taker_pos_streak"] = streak.clip(-10, 10)
    return out


class BinanceTakerFlowSource(SignalSource):
    name = "takerflow"
    feature_prefix = "tf_"
    requires = ("ohlcv_eval",)

    def __init__(self, metrics_5m: pd.DataFrame) -> None:
        self.metrics_5m = metrics_5m

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        if self.metrics_5m is None or len(self.metrics_5m) == 0:
            return pd.DataFrame(index=ctx.ohlcv_eval.index)

        daily = _build_taker_daily(self.metrics_5m)
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
