"""USDailySource — 미국 ETF 일봉 파생 피처.

키움 미국 일봉(usa06012)만으로 만들 수 있는 substrate. 6.7년치가 이미 적재돼
있어 R-0~R-4 전 과정을 즉시 돌릴 수 있다.

이 소스가 존재하는 이유:
    기존 25개 소스가 전부 binance_* 이고, funding/OI/premium 은 미국주식에
    존재하지 않는 개념이라 이식 불가다. 범용 소스(pattern/mkt/regime)는 있지만
    미국장 고유 구조(오버나이트 세션, 갭, 정규장 391분)를 전혀 모른다.

미국 일봉의 특수성 — 반드시 알고 쓸 것:
    이 일봉의 종가는 정규장 종가가 아니라 연장·오버나이트(Blue Ocean, ET
    20:00~04:00) 체결까지 반영한 그 영업일의 최종가다. 시가는 정규장 시가와
    일치한다(실측 괴리 중앙 0.001~0.06%).

    따라서 `gap` = 당일 시가 / 전일 종가 - 1 은 통상적 의미의 "야간 갭"이 아니라
    **오버나이트 세션 종료가 대비 정규장 시가의 괴리**다. 한국 야간 세션에서
    형성된 가격이 미국 정규장 개장에서 얼마나 되돌려지는지를 보는 지표이며,
    이건 미국 현지 데이터로는 만들 수 없는 고유 신호다.

피처:
    gap                전일 종가 → 당일 시가 괴리
    gap_z              gap 의 z-score (lookback)
    intraday_ret       당일 시가 → 종가 (오버나이트 포함 최종가 기준)
    overnight_ret      전일 종가 → 당일 종가 중 시가 이후 몫을 제외한 잔차
    range_pct          (고가-저가)/시가
    pos_52w            52주 고저 구간 내 위치 (0=저점, 1=고점)
    dist_high_52w      52주 신고가 대비 하락률
    vol_z              거래량 z-score
    ret_1 / ret_5 / ret_20   누적 수익률
    streak             연속 상승(+)/하락(-) 일수
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext


class USDailySource(SignalSource):
    name = "us_daily"
    feature_prefix = "usd_"
    requires = ("ohlcv_eval",)

    def __init__(self, *, z_lookback: int = 60, high_low_window: int = 252) -> None:
        self.z_lookback = max(int(z_lookback), 5)
        self.high_low_window = max(int(high_low_window), 20)

    @staticmethod
    def _zscore(s: pd.Series, window: int) -> pd.Series:
        mean = s.rolling(window, min_periods=max(window // 3, 3)).mean()
        std = s.rolling(window, min_periods=max(window // 3, 3)).std(ddof=0)
        return ((s - mean) / std.replace(0.0, np.nan)).replace([np.inf, -np.inf], np.nan)

    @staticmethod
    def _streak(returns: pd.Series) -> pd.Series:
        """연속 상승/하락 일수. 상승 연속은 +n, 하락 연속은 -n."""
        sign = np.sign(returns.fillna(0.0).to_numpy())
        out = np.zeros(len(sign))
        run = 0
        for i, s in enumerate(sign):
            if s > 0:
                run = run + 1 if run > 0 else 1
            elif s < 0:
                run = run - 1 if run < 0 else -1
            else:
                run = 0
            out[i] = run
        return pd.Series(out, index=returns.index)

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        df = ctx.ohlcv_eval
        out = pd.DataFrame(index=df.index)

        open_, high, low, close = df["open"], df["high"], df["low"], df["close"]
        volume = df["volume"]
        prev_close = close.shift(1)

        gap = (open_ / prev_close - 1.0).replace([np.inf, -np.inf], np.nan)
        out["gap"] = gap
        out["gap_z"] = self._zscore(gap, self.z_lookback)

        intraday = (close / open_ - 1.0).replace([np.inf, -np.inf], np.nan)
        out["intraday_ret"] = intraday
        # 전일 종가 대비 총수익 중 정규장 개장 이후로 설명되지 않는 몫
        out["overnight_ret"] = gap

        out["range_pct"] = ((high - low) / open_.replace(0.0, np.nan)).replace(
            [np.inf, -np.inf], np.nan)

        window = self.high_low_window
        min_p = max(window // 4, 20)
        roll_high = high.rolling(window, min_periods=min_p).max()
        roll_low = low.rolling(window, min_periods=min_p).min()
        span = (roll_high - roll_low).replace(0.0, np.nan)
        out["pos_52w"] = ((close - roll_low) / span).clip(0.0, 1.0)
        out["dist_high_52w"] = (close / roll_high - 1.0).replace([np.inf, -np.inf], np.nan)

        out["vol_z"] = self._zscore(volume.astype(float), self.z_lookback)

        for n in (1, 5, 20):
            out[f"ret_{n}"] = close.pct_change(n).replace([np.inf, -np.inf], np.nan)

        out["streak"] = self._streak(close.pct_change())

        return self._prefixed(out)
