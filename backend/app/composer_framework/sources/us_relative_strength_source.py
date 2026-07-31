"""USRelativeStrengthSource — 벤치마크(기본 SPY) 대비 상대강도.

왜 필요한가:
    ETF 유니버스는 섹터·지역·자산군이 섞여 있어 절대 수익률만 보면 결국
    "시장이 올랐나"만 측정하게 된다. 코어 60종이 대부분 미국 주식 베타에
    노출돼 있어서, 개별 ETF 신호는 벤치마크를 빼야 의미가 생긴다.

    바이낸스 트랙의 bn_cross_lead_lag 가 BTC 를 리더로 두는 것과 같은 자리를,
    미국 ETF 에서는 SPY 가 맡는다.

입력:
    leader_ohlcv_eval — 벤치마크 일봉 (paper_session_cli 가 로드해 주입)
    없으면 전 구간 NaN 을 돌려주고 경고. 파이프라인을 죽이지는 않는다.

피처:
    rs_ret_{n}    n일 초과수익 (심볼 - 벤치마크)
    rs_ratio      가격비(sym/bench)의 정규화 값 — 1.0 = lookback 시작 시점 동일
    rs_ratio_z    가격비 z-score
    rs_slope_20   가격비 20일 회귀 기울기 (추세 지속성)
    beta_60       60일 회귀 베타
    corr_60       60일 상관계수
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext

logger = logging.getLogger(__name__)


class USRelativeStrengthSource(SignalSource):
    name = "us_rs"
    feature_prefix = "usrs_"
    requires = ("ohlcv_eval",)

    def __init__(self, benchmark_df: pd.DataFrame | None = None, *,
                 benchmark_symbol: str = "SPY", z_lookback: int = 60,
                 beta_window: int = 60) -> None:
        self.benchmark_df = benchmark_df
        self.benchmark_symbol = benchmark_symbol
        self.z_lookback = max(int(z_lookback), 10)
        self.beta_window = max(int(beta_window), 20)

    @staticmethod
    def _slope(s: pd.Series, window: int) -> pd.Series:
        """rolling 선형회귀 기울기 (x = 0..window-1, 정규화된 y 기준)."""
        x = np.arange(window, dtype=float)
        x_centered = x - x.mean()
        denom = (x_centered ** 2).sum()

        def _fit(vals: np.ndarray) -> float:
            if np.isnan(vals).any():
                return np.nan
            return float((x_centered * (vals - vals.mean())).sum() / denom)

        return s.rolling(window, min_periods=window).apply(_fit, raw=True)

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        df = ctx.ohlcv_eval
        out = pd.DataFrame(index=df.index)

        if self.benchmark_df is None or self.benchmark_df.empty:
            logger.warning(
                "[us_rs] 벤치마크(%s) 미주입 — 전 구간 NaN 반환",
                self.benchmark_symbol,
            )
            for col in ("rs_ret_1", "rs_ret_5", "rs_ret_20", "rs_ratio",
                        "rs_ratio_z", "rs_slope_20", "beta_60", "corr_60"):
                out[col] = np.nan
            return self._prefixed(out)

        bench = self.benchmark_df["close"].reindex(df.index).ffill()
        close = df["close"]

        sym_ret = close.pct_change()
        bench_ret = bench.pct_change()

        for n in (1, 5, 20):
            out[f"rs_ret_{n}"] = (
                close.pct_change(n) - bench.pct_change(n)
            ).replace([np.inf, -np.inf], np.nan)

        ratio = (close / bench.replace(0.0, np.nan)).replace([np.inf, -np.inf], np.nan)
        base = ratio.rolling(self.z_lookback, min_periods=self.z_lookback).apply(
            lambda v: v[0], raw=True)
        out["rs_ratio"] = (ratio / base).replace([np.inf, -np.inf], np.nan)

        mean = ratio.rolling(self.z_lookback, min_periods=self.z_lookback // 3).mean()
        std = ratio.rolling(self.z_lookback, min_periods=self.z_lookback // 3).std(ddof=0)
        out["rs_ratio_z"] = ((ratio - mean) / std.replace(0.0, np.nan)).replace(
            [np.inf, -np.inf], np.nan)

        out["rs_slope_20"] = self._slope(np.log(ratio.replace(0.0, np.nan)), 20)

        w = self.beta_window
        cov = sym_ret.rolling(w, min_periods=w // 2).cov(bench_ret)
        var = bench_ret.rolling(w, min_periods=w // 2).var(ddof=0)
        out["beta_60"] = (cov / var.replace(0.0, np.nan)).replace([np.inf, -np.inf], np.nan)
        out["corr_60"] = sym_ret.rolling(w, min_periods=w // 2).corr(bench_ret)

        return self._prefixed(out)
