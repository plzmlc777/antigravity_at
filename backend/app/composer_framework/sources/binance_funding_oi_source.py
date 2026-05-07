"""BinanceFundingOISource — funding rate + Open Interest history features.

Hypothesis: KR Flow 같은 결정적 누적 positioning 신호가 Binance에도 존재한다면,
가장 가능성 높은 후보는 (a) 8h funding rate 누적과 (b) daily OI 변화율.

Funding rate (8h granularity):
  - long-pay-short → 매수측 누적 비용 (positive = 롱이 우세, 다음 가격 하락 압력 잠재)
  - 누적 sum/zscore가 mean reversion 신호로 작용 가능

Open Interest (1d granularity, last 30d 한도):
  - 가격 상승 + OI 증가  → 진성 추세 (pile-in)
  - 가격 상승 + OI 감소  → 숏 커버 (취약 추세)
  - 가격 하락 + OI 증가  → 진성 매도
  - delta + zscore로 positioning 변동 캡처

Output (모든 컬럼 prefix `bn_`):
  bn_funding_mean_1d, bn_funding_sum_1d, bn_funding_std_1d,
  bn_funding_5d_cum, bn_funding_20d_cum, bn_funding_zscore_60d,
  bn_oi_log,
  bn_oi_pct_change_1d, bn_oi_5d_cum_change, bn_oi_zscore_30d
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext


def _build_funding_daily(funding_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate 8h funding records to daily features (UTC-day buckets)."""
    if funding_df is None or len(funding_df) == 0:
        return pd.DataFrame()
    f = funding_df.copy()
    f["funding_time"] = pd.to_datetime(f["funding_time"])
    f["funding_rate"] = pd.to_numeric(f["funding_rate"], errors="coerce")
    f = f.dropna(subset=["funding_time", "funding_rate"])
    if f.empty:
        return pd.DataFrame()
    f["date"] = f["funding_time"].dt.normalize()
    daily = f.groupby("date")["funding_rate"].agg(
        funding_mean_1d="mean",
        funding_sum_1d="sum",
        funding_std_1d="std",
    )
    daily["funding_5d_cum"] = daily["funding_sum_1d"].rolling(5, min_periods=2).sum()
    daily["funding_20d_cum"] = daily["funding_sum_1d"].rolling(20, min_periods=5).sum()
    rolling_mean = daily["funding_mean_1d"].rolling(60, min_periods=20).mean()
    rolling_std = daily["funding_mean_1d"].rolling(60, min_periods=20).std()
    daily["funding_zscore_60d"] = (daily["funding_mean_1d"] - rolling_mean) / rolling_std.replace(0, np.nan)
    return daily


def _build_oi_daily(oi_df: pd.DataFrame) -> pd.DataFrame:
    """Build daily OI features. Expects 1d period rows; if multiple intervals
    are stored, only `interval_str == '1d'` rows are used."""
    if oi_df is None or len(oi_df) == 0:
        return pd.DataFrame()
    o = oi_df.copy()
    if "interval_str" in o.columns:
        o = o[o["interval_str"] == "1d"]
    if o.empty:
        return pd.DataFrame()
    o["timestamp"] = pd.to_datetime(o["timestamp"])
    o["sum_open_interest"] = pd.to_numeric(o["sum_open_interest"], errors="coerce")
    o = o.dropna(subset=["timestamp", "sum_open_interest"])
    if o.empty:
        return pd.DataFrame()
    o["date"] = o["timestamp"].dt.normalize()
    daily = o.groupby("date")["sum_open_interest"].mean().to_frame("oi")
    daily = daily.sort_index()
    daily["oi_log"] = np.log(daily["oi"].clip(lower=1e-9))
    daily["oi_pct_change_1d"] = daily["oi"].pct_change(fill_method=None)
    daily["oi_5d_cum_change"] = daily["oi_pct_change_1d"].rolling(5, min_periods=2).sum()
    rolling_mean = daily["oi"].rolling(30, min_periods=10).mean()
    rolling_std = daily["oi"].rolling(30, min_periods=10).std()
    daily["oi_zscore_30d"] = (daily["oi"] - rolling_mean) / rolling_std.replace(0, np.nan)
    return daily.drop(columns=["oi"])


class BinanceFundingOISource(SignalSource):
    name = "bnfundingoi"
    feature_prefix = "bn_"
    requires = ("ohlcv_eval",)

    def __init__(
        self,
        funding_df: pd.DataFrame | None = None,
        oi_df: pd.DataFrame | None = None,
    ) -> None:
        self.funding_df = funding_df
        self.oi_df = oi_df

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        eval_idx = pd.to_datetime(ctx.ohlcv_eval.index)
        out = pd.DataFrame(index=eval_idx)

        # Map daily features onto eval index by date (forward-fill).
        eval_norm = eval_idx.normalize()

        funding_daily = _build_funding_daily(self.funding_df)
        if not funding_daily.empty:
            funding_daily = funding_daily[~funding_daily.index.duplicated(keep="last")]
            mapped_f = funding_daily.reindex(
                pd.DatetimeIndex(sorted(set(funding_daily.index) | set(eval_norm)))
            ).ffill().reindex(eval_norm)
            mapped_f.index = eval_idx
            for c in mapped_f.columns:
                out[c] = mapped_f[c]

        oi_daily = _build_oi_daily(self.oi_df)
        if not oi_daily.empty:
            oi_daily = oi_daily[~oi_daily.index.duplicated(keep="last")]
            mapped_o = oi_daily.reindex(
                pd.DatetimeIndex(sorted(set(oi_daily.index) | set(eval_norm)))
            ).ffill().reindex(eval_norm)
            mapped_o.index = eval_idx
            for c in mapped_o.columns:
                out[c] = mapped_o[c]

        return self._prefixed(out)
