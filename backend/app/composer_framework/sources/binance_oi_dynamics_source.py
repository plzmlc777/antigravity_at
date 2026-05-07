"""BinanceOIDynamicsSource — joint dynamics of Open Interest × price.

Hypothesis: OI 자체는 결정적이지 않지만 (B-3 검증), OI 변화 × 가격 변화
조합은 trader behavior 신호:

  +ΔOI + +ΔPrice  → long pile-in (강한 추세)
  -ΔOI + +ΔPrice  → short cover squeeze (약한 추세)
  +ΔOI + -ΔPrice  → short pile-in (강한 약세)
  -ΔOI + -ΔPrice  → long capitulation (탈출)

KR Flow에서 외인 누적 매수가 결정적이듯, 이 4-quadrant signal의 일관 누적이
trend-quality indicator로 작용 가능.

Output (prefix `oid_`):
  oid_oi_pct_1d                  — daily OI mean % change
  oid_price_pct_1d               — daily close-to-close % change
  oid_quad                       — 4-quadrant categorical (encoded as 1..4 int)
  oid_pile_in_score_1d           — sign(ΔOI) * sign(ΔPrice) (in {-1, 0, +1})
  oid_pile_in_5d_cum             — 5d sum of pile_in_score
  oid_pile_in_20d_cum
  oid_oi_price_corr_20d          — rolling 20d corr(ΔOI, ΔPrice)
  oid_oi_change_zscore_30d
  oid_strong_trend_score         — |ΔOI%|*sign(ΔPrice) (magnitude × direction)
  oid_strong_trend_5d_cum
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext


def _build_oi_dynamics_daily(metrics_5m: pd.DataFrame, ohlcv_eval: pd.DataFrame) -> pd.DataFrame:
    if metrics_5m is None or metrics_5m.empty or "open_interest" not in metrics_5m.columns:
        return pd.DataFrame()
    df = metrics_5m.copy()
    df = df.replace(0.0, np.nan)
    df["open_interest"] = pd.to_numeric(df["open_interest"], errors="coerce")
    df = df.dropna(subset=["open_interest"])
    if df.empty:
        return pd.DataFrame()
    g = df.resample("1D", origin="start_day")
    daily_oi = g["open_interest"].mean()

    # Daily price (use ohlcv_eval close, normalized to UTC date)
    eval_close = ohlcv_eval["close"]
    eval_close.index = pd.to_datetime(eval_close.index).normalize()
    daily_price = eval_close.groupby(eval_close.index).last()

    df_d = pd.concat([daily_oi.rename("oi"), daily_price.rename("price")], axis=1)
    df_d = df_d.dropna(how="any")
    if len(df_d) < 5:
        return pd.DataFrame()

    out = pd.DataFrame(index=df_d.index)
    out["oi_pct_1d"] = df_d["oi"].pct_change(fill_method=None)
    out["price_pct_1d"] = df_d["price"].pct_change(fill_method=None)

    # 4-quadrant encoding (1=long pile-in, 2=short cover, 3=short pile-in, 4=long cap)
    pos_oi = (out["oi_pct_1d"] > 0).astype(int)
    pos_pr = (out["price_pct_1d"] > 0).astype(int)
    quad = np.where(pos_oi == 1,
                    np.where(pos_pr == 1, 1, 3),
                    np.where(pos_pr == 1, 2, 4))
    out["quad"] = quad

    pile_in = np.sign(out["oi_pct_1d"]) * np.sign(out["price_pct_1d"])  # {-1,0,+1}
    out["pile_in_score_1d"] = pile_in
    out["pile_in_5d_cum"] = out["pile_in_score_1d"].rolling(5, min_periods=2).sum()
    out["pile_in_20d_cum"] = out["pile_in_score_1d"].rolling(20, min_periods=5).sum()

    out["oi_price_corr_20d"] = (
        out["oi_pct_1d"].rolling(20, min_periods=10).corr(out["price_pct_1d"])
    )

    rmean30 = out["oi_pct_1d"].rolling(30, min_periods=10).mean()
    rstd30 = out["oi_pct_1d"].rolling(30, min_periods=10).std()
    out["oi_change_zscore_30d"] = (out["oi_pct_1d"] - rmean30) / rstd30.replace(0, np.nan)

    out["strong_trend_score"] = out["oi_pct_1d"].abs() * np.sign(out["price_pct_1d"])
    out["strong_trend_5d_cum"] = out["strong_trend_score"].rolling(5, min_periods=2).sum()
    return out


class BinanceOIDynamicsSource(SignalSource):
    name = "oidynamics"
    feature_prefix = "oid_"
    requires = ("ohlcv_eval",)

    def __init__(self, metrics_5m: pd.DataFrame) -> None:
        self.metrics_5m = metrics_5m

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        if self.metrics_5m is None or len(self.metrics_5m) == 0:
            return pd.DataFrame(index=ctx.ohlcv_eval.index)

        daily = _build_oi_dynamics_daily(self.metrics_5m, ctx.ohlcv_eval)
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
