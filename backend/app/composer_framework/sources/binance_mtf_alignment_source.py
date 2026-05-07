"""BinanceMTFAlignmentSource — Multi-Timeframe momentum alignment.

Binance 24/7 환경에서 5min/1h/4h momentum 정렬도가 결정적. KR 일별 매크로와
달리 intraday 다중 시간대 일치/불일치가 단기 trade 신호로 작용.

Hypothesis:
  - All bullish (5m+1h+4h same dir) → strong continuation
  - Diverging (5m flip vs 1h+4h) → mean reversion candidate
  - 1h leads 5m (1h trend + 5m pullback) → entry timing

Output (prefix `mtf_`):
  mtf_5m_ret_zscore_1d         — 5min realized return zscore vs 24h
  mtf_1h_ret_1d                — last 1h cumulative return (close-of-day)
  mtf_4h_ret_1d                — last 4h cumulative return
  mtf_alignment_score          — sign(5m) + sign(1h) + sign(4h) ∈ {-3..+3}
  mtf_alignment_pct_1d         — daily fraction with all-aligned (|score|=3)
  mtf_5m_volatility_1d         — std of 5min returns over the day
  mtf_5m_vol_zscore_60d        — daily vol zscore vs 60-day
  mtf_drift_efficiency_1d      — |1h_ret| / sum(|5m_ret|) (trend smoothness)
  mtf_5m_to_4h_correlation_1d  — daily corr(5m_returns, 4h returns at 5min idx)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext


def _build_mtf_features(ohlcv_1m: pd.DataFrame) -> pd.DataFrame:
    if ohlcv_1m is None or ohlcv_1m.empty:
        return pd.DataFrame()

    # Resample to 5min, 1h, 4h
    c5 = ohlcv_1m["close"].resample("5min").last().dropna()
    c1h = ohlcv_1m["close"].resample("1h").last().dropna()
    c4h = ohlcv_1m["close"].resample("4h").last().dropna()
    if len(c5) < 200 or len(c1h) < 30 or len(c4h) < 10:
        return pd.DataFrame()

    ret5 = c5.pct_change(fill_method=None)
    ret1h = c1h.pct_change(fill_method=None)
    ret4h = c4h.pct_change(fill_method=None)

    # Project 1h and 4h returns onto 5min index (forward-fill)
    ret1h_at_5m = ret1h.reindex(c5.index, method="ffill")
    ret4h_at_5m = ret4h.reindex(c5.index, method="ffill")

    sig5 = np.sign(ret5)
    sig1h = np.sign(ret1h_at_5m)
    sig4h = np.sign(ret4h_at_5m)
    align = (sig5.fillna(0) + sig1h.fillna(0) + sig4h.fillna(0))

    df5 = pd.DataFrame({
        "ret5": ret5,
        "ret1h": ret1h_at_5m,
        "ret4h": ret4h_at_5m,
        "align": align,
    })

    # Daily aggregation
    g = df5.resample("1D", origin="start_day")
    out = pd.DataFrame(index=g["ret5"].mean().index)
    # 5min realized vol (std of 5min returns) per day
    out["5m_volatility_1d"] = g["ret5"].std()
    # Last 1h/4h returns per day (close-of-day)
    out["1h_ret_1d"] = g["ret1h"].last()
    out["4h_ret_1d"] = g["ret4h"].last()
    # 5m return zscore vs 24h (using last 5m return / day std)
    out["5m_ret_zscore_1d"] = g["ret5"].apply(
        lambda s: (s.iloc[-1] / s.std()) if len(s) > 1 and s.std() > 0 else np.nan
    )
    # Alignment score (last bar's value) and daily fraction with full alignment
    out["alignment_score"] = g["align"].apply(lambda s: s.iloc[-1] if len(s) else np.nan)
    out["alignment_pct_1d"] = g["align"].apply(lambda s: float((s.abs() == 3).mean()) if len(s) else np.nan)

    # Trend efficiency: |1h ret| / sum |5m ret|
    sum_abs_5m = g["ret5"].apply(lambda s: s.abs().sum() if len(s) else np.nan)
    out["drift_efficiency_1d"] = (out["1h_ret_1d"].abs() / sum_abs_5m.replace(0, np.nan)).clip(0, 1)

    # 5m vol zscore vs 60d
    rmean = out["5m_volatility_1d"].rolling(60, min_periods=20).mean()
    rstd = out["5m_volatility_1d"].rolling(60, min_periods=20).std()
    out["5m_vol_zscore_60d"] = (out["5m_volatility_1d"] - rmean) / rstd.replace(0, np.nan)

    # 5m vs 4h correlation per day (5m returns vs forward-filled 4h return)
    out["5m_to_4h_correlation_1d"] = g.apply(
        lambda sub: sub["ret5"].corr(sub["ret4h"]) if len(sub) > 5 else np.nan
    )
    return out


class BinanceMTFAlignmentSource(SignalSource):
    name = "mtf"
    feature_prefix = "mtf_"
    requires = ("ohlcv_1m",)

    def __init__(self) -> None:
        pass

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        if ctx.ohlcv_1m is None or ctx.ohlcv_1m.empty:
            return pd.DataFrame(index=ctx.ohlcv_eval.index)

        daily = _build_mtf_features(ctx.ohlcv_1m)
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
