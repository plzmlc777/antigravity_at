"""BinanceCascadeReversalSource — liquidation cascade detection + post-event reversal.

Binance perpetual futures의 가장 결정적 dynamic은 leveraged liquidation cascade.
Cascade event = 5min vol spike + OI rapid drop + taker imbalance flip.
Cascade 직후에는 mean reversion이 잦음 (forced liquidation 압력 해소).

Hypothesis:
  - Long cascade (price ↓ + OI ↓ + taker turns sell-heavy) → 1-4h 후 reversion ↑
  - Short cascade (price ↑ + OI ↓ + taker turns buy-heavy) → 1-4h 후 reversion ↓

Output (prefix `cr_`):
  cr_long_cascade_count_1d
  cr_short_cascade_count_1d
  cr_total_cascade_count_5d_sum
  cr_long_cascade_revert_1d   — avg post-event 4h return after long cascade (>0 = reverted up)
  cr_short_cascade_revert_1d  — avg post-event 4h return after short cascade (<0 = reverted down)
  cr_cascade_intensity_1d     — sum(|5min_ret| × cascade_flag)
  cr_recent_cascade_age_bars  — bars since last cascade (0 = today)
  cr_post_cascade_continue_score — fraction of cascades that CONTINUED in same dir (vs reverted)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext


def _build_cascade_features(metrics_5m: pd.DataFrame, ohlcv_5m: pd.DataFrame) -> pd.DataFrame:
    if metrics_5m is None or metrics_5m.empty: return pd.DataFrame()
    if ohlcv_5m is None or ohlcv_5m.empty: return pd.DataFrame()

    df = pd.concat([
        ohlcv_5m["close"].rename("close"),
        metrics_5m["open_interest"],
        metrics_5m["taker_buy_sell_ratio"],
    ], axis=1, join="inner").dropna()
    if len(df) < 200:
        return pd.DataFrame()

    df["ret"] = df["close"].pct_change(fill_method=None)
    df["oi_chg"] = df["open_interest"].pct_change(fill_method=None)
    df["taker_skew"] = (df["taker_buy_sell_ratio"] - 1)

    ret_std = df["ret"].rolling(200, min_periods=50).std()
    oi_std = df["oi_chg"].rolling(200, min_periods=50).std()

    # Cascade definitions:
    # Long cascade (long liquidation): big drop + OI drop + taker turns negative
    long_cascade = (
        (df["ret"] < -2 * ret_std)
        & (df["oi_chg"] < -1.5 * oi_std)
        & (df["taker_skew"] < -0.3)
    )
    # Short cascade (short squeeze): big up + OI drop + taker turns positive
    short_cascade = (
        (df["ret"] > 2 * ret_std)
        & (df["oi_chg"] < -1.5 * oi_std)
        & (df["taker_skew"] > 0.3)
    )
    df["long_cascade"] = long_cascade
    df["short_cascade"] = short_cascade
    df["any_cascade"] = long_cascade | short_cascade

    # Post-event (next 48 5min bars = 4h) signed return
    forward_4h = df["close"].shift(-48) / df["close"] - 1
    # For long cascade, revert means forward > 0 (price up after drop)
    df["long_cascade_revert"] = np.where(long_cascade, forward_4h, np.nan)
    # For short cascade, revert means forward < 0 (price down after spike)
    df["short_cascade_revert"] = np.where(short_cascade, forward_4h, np.nan)
    df["cascade_intensity"] = df["any_cascade"].astype(float) * df["ret"].abs()

    # Daily aggregation
    g = df.resample("1D", origin="start_day")
    out = pd.DataFrame(index=g["close"].mean().index)
    out["long_cascade_count_1d"] = g["long_cascade"].sum()
    out["short_cascade_count_1d"] = g["short_cascade"].sum()
    total = out["long_cascade_count_1d"] + out["short_cascade_count_1d"]
    out["total_cascade_count_5d_sum"] = total.rolling(5, min_periods=2).sum()
    out["long_cascade_revert_1d"] = g["long_cascade_revert"].mean()
    out["short_cascade_revert_1d"] = g["short_cascade_revert"].mean()
    out["cascade_intensity_1d"] = g["cascade_intensity"].sum()

    # Recency: bars since last cascade
    casc_idx = df.index[df["any_cascade"]]
    if len(casc_idx) > 0:
        bars_since = (~df["any_cascade"]).groupby(df["any_cascade"].cumsum()).cumcount()
        df["bars_since_cascade"] = bars_since
        out["recent_cascade_age_bars"] = df["bars_since_cascade"].resample("1D", origin="start_day").mean()
    else:
        out["recent_cascade_age_bars"] = np.nan

    # Continue vs revert score: fraction where forward 4h same sign as cascade direction
    long_cont = (long_cascade & (forward_4h < 0)).resample("1D", origin="start_day").sum()
    short_cont = (short_cascade & (forward_4h > 0)).resample("1D", origin="start_day").sum()
    cont_total = long_cont + short_cont
    out["post_cascade_continue_score"] = (cont_total / total.replace(0, np.nan)).reindex(out.index)

    return out


class BinanceCascadeReversalSource(SignalSource):
    name = "cascade"
    feature_prefix = "cr_"
    requires = ("ohlcv_1m",)

    def __init__(self, metrics_5m: pd.DataFrame) -> None:
        self.metrics_5m = metrics_5m

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        if ctx.ohlcv_1m is None or ctx.ohlcv_1m.empty:
            return pd.DataFrame(index=ctx.ohlcv_eval.index)
        if self.metrics_5m is None or self.metrics_5m.empty:
            return pd.DataFrame(index=ctx.ohlcv_eval.index)

        ohlcv_5m = ctx.ohlcv_1m["close"].resample("5min").last().to_frame("close").dropna()
        daily = _build_cascade_features(self.metrics_5m, ohlcv_5m)
        if daily.empty:
            return pd.DataFrame(index=ctx.ohlcv_eval.index)

        eval_idx = pd.to_datetime(ctx.ohlcv_eval.index)
        eval_norm = eval_idx.normalize()
        daily.index = pd.to_datetime(daily.index).normalize()
        daily = daily[~daily.index.duplicated(keep="last")]
        mapped = daily.reindex(
            pd.DatetimeIndex(sorted(set(daily.index) | set(eval_norm)))
        ).ffill().reindex(eval_norm)
        mapped.index = eval_idx
        return self._prefixed(mapped)
