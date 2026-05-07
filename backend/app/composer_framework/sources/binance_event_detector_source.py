"""BinanceEventDetectorSource — 5min spike/burst/cascade detection.

Binance native 24/7 high-frequency liquidation environment에서는 5min 단위
이벤트(vol spike, OI surge, taker imbalance flip)가 결정적이다. Daily aggregation
누적 (KR Flow 패턴)이 아닌 'event 빈도 + 직후 가격 행동' 직접 측정.

Hypothesis: liquidation cascade 직후 mean reversion / continuation pattern.
Daily feature는 직전 N일의 event 통계.

Output (prefix `ev_`):
  ev_vol_spike_count_1d        — 5min |ret|>2σ events / day
  ev_oi_surge_count_1d         — 5min OI Δ>2σ events / day
  ev_taker_burst_count_1d      — 5min |taker_imbalance|>0.7 events / day
  ev_triple_event_count_1d     — vol+oi+taker simultaneous (cascade proxy)
  ev_event_count_5d_sum
  ev_max_5min_abs_return_1d    — biggest 5min move
  ev_max_5min_oi_change_1d     — biggest OI move
  ev_post_spike_revert_1d      — avg price reversion in next 12 bars (1h) after vol spike
  ev_post_spike_continue_1d    — avg continuation in same direction
  ev_event_recency             — bars since last triple event
  ev_event_intensity_1d        — sum(|ret|*event_weight)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext


def _detect_events_and_aggregate(
    metrics_5m: pd.DataFrame,
    ohlcv_5m: pd.DataFrame,
) -> pd.DataFrame:
    """Detect 5min events from metrics + ohlcv, aggregate to daily."""
    if metrics_5m is None or metrics_5m.empty:
        return pd.DataFrame()
    if ohlcv_5m is None or ohlcv_5m.empty:
        return pd.DataFrame()

    # Align indexes by inner join (5min level)
    df = pd.concat([
        ohlcv_5m["close"].rename("close"),
        metrics_5m["open_interest"],
        metrics_5m["taker_buy_sell_ratio"],
    ], axis=1, join="inner").dropna()
    if len(df) < 200:
        return pd.DataFrame()

    # 5min returns
    df["ret"] = df["close"].pct_change(fill_method=None)
    # OI change
    df["oi_chg"] = df["open_interest"].pct_change(fill_method=None)
    # Taker imbalance (centered around 1)
    df["taker_imb"] = (df["taker_buy_sell_ratio"] - 1) / (df["taker_buy_sell_ratio"] + 1)

    # Rolling 200-bar (~17h) std as event threshold reference
    ret_std = df["ret"].rolling(200, min_periods=50).std()
    oi_std = df["oi_chg"].rolling(200, min_periods=50).std()

    # Boolean event flags
    df["vol_spike"] = df["ret"].abs() > 2 * ret_std
    df["oi_surge"] = df["oi_chg"].abs() > 2 * oi_std
    df["taker_burst"] = df["taker_imb"].abs() > 0.4  # 0.4 = ratio 2.33+ or 0.43-
    df["triple_event"] = df["vol_spike"] & df["oi_surge"] & df["taker_burst"]
    df["event_intensity"] = df["ret"].abs() * (
        df["vol_spike"].astype(float)
        + df["oi_surge"].astype(float)
        + df["taker_burst"].astype(float)
    )

    # Post-spike behavior: 12 5min-bars (1h) ahead
    forward = df["close"].shift(-12) / df["close"] - 1
    df["post_spike_signed"] = np.where(df["vol_spike"], np.sign(df["ret"]) * forward, np.nan)
    df["post_spike_revert"] = -df["post_spike_signed"]  # if revert, price goes opposite of spike → positive
    df["post_spike_continue"] = df["post_spike_signed"]  # if continue, same dir → positive

    # Aggregate to daily
    g = df.resample("1D", origin="start_day")
    out = pd.DataFrame(index=g["close"].mean().index)
    out["vol_spike_count_1d"] = g["vol_spike"].sum()
    out["oi_surge_count_1d"] = g["oi_surge"].sum()
    out["taker_burst_count_1d"] = g["taker_burst"].sum()
    out["triple_event_count_1d"] = g["triple_event"].sum()
    out["event_count_5d_sum"] = (
        out["vol_spike_count_1d"] + out["oi_surge_count_1d"] + out["taker_burst_count_1d"]
    ).rolling(5, min_periods=2).sum()
    out["max_5min_abs_return_1d"] = g["ret"].apply(lambda s: s.abs().max() if len(s) else np.nan)
    out["max_5min_oi_change_1d"] = g["oi_chg"].apply(lambda s: s.abs().max() if len(s) else np.nan)
    out["post_spike_revert_1d"] = g["post_spike_revert"].mean()
    out["post_spike_continue_1d"] = g["post_spike_continue"].mean()
    out["event_intensity_1d"] = g["event_intensity"].sum()

    # Event recency: bars since last triple event (in days)
    triple_idx = df.index[df["triple_event"]]
    if len(triple_idx) > 0:
        last_triple = pd.Series(np.nan, index=df.index)
        for ts in triple_idx:
            last_triple.loc[ts:] = 0
        bars_since = (~df["triple_event"]).groupby(df["triple_event"].cumsum()).cumcount()
        df["bars_since_triple"] = bars_since
        # daily mean of bars_since (lower = recent)
        out["event_recency"] = df["bars_since_triple"].resample("1D", origin="start_day").mean()
    else:
        out["event_recency"] = np.nan

    return out


class BinanceEventDetectorSource(SignalSource):
    name = "events"
    feature_prefix = "ev_"
    requires = ("ohlcv_1m",)

    def __init__(self, metrics_5m: pd.DataFrame) -> None:
        self.metrics_5m = metrics_5m

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        if ctx.ohlcv_1m is None or ctx.ohlcv_1m.empty:
            return pd.DataFrame(index=ctx.ohlcv_eval.index)
        if self.metrics_5m is None or self.metrics_5m.empty:
            return pd.DataFrame(index=ctx.ohlcv_eval.index)

        # Resample 1m → 5m
        ohlcv_5m = ctx.ohlcv_1m["close"].resample("5min").last().to_frame("close").dropna()

        daily = _detect_events_and_aggregate(self.metrics_5m, ohlcv_5m)
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
