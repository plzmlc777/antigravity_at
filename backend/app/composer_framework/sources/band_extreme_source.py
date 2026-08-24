"""BandExtremeSource — 볼린저 밴드 극단 진입 신호. 익절·손절은 정책이 맡는다.

왜 이 신호원인가 (2026-08-22 중복도 검사)
    376종목 1년 5분봉에서 지표 11종의 발화 시점을 **같은 빈도로 맞춰** 비교한
    결과, RSI(14)와 가장 겹치지 않는 것이 **볼린저 하단 이탈**이었다
    (자카드 0.170). 눈금은 이렇다 — 같은 RSI를 기간만 14→21로 바꾸면 0.835,
    같은 지표를 평활만 바꾸면 0.676. 0.170 은 그보다 한참 아래다.
    볼린저 신호 7,262건 중 6,018건(82.9%)이 RSI가 못 보는 자리였다.

    ⚠ z-score 진입은 이것과 **수학적으로 동일**하다.
      (c <= ma - k·sd) ⟺ ((c-ma)/sd <= -k). 별도 후보가 아니다.

규칙
    z = (close - SMA(period)) / STD(period, ddof=0)
    롱 : z <= -sigma        (하단 이탈 = 과매도)
    숏 : z >= +sigma        (상단 이탈 = 과매수)
    `side` 로 방향을 고른다. **같은 설정의 거울**을 항상 같이 돌린다 (교훈 #91).

⚠ 미래참조 없음
    SMA·STD 는 t 시점 종가까지만 쓴다(rolling, center 없음). 체결은 커널이
    `signal_lag_bars=1` 로 다음 봉 시가에 낸다. 소스에서 추가로 밀지 않는다
    (교훈 #90).

⚠ 데이터 결손은 **0 신호로 감추지 않는다**
    봉이 모자라면 `InsufficientSourceDataError`.

⚠ 위약은 공용 구현 하나를 쓴다
    `rsi_threshold_source.apply_entry_placebo`. 신호원마다 복사하면 대조군이
    소스마다 달라져 비교가 성립하지 않는다.

출력 (prefix `band_`)
    band_signal — {-1.0, 0.0, +1.0}
    band_z      — z 원값 (디버그·진단용)

조합: `PassthroughComposer`(feature_col=band_signal) +
      `LongShortThresholdPolicy`(entry_threshold=0.5, sl_pct, tp_pct,
                                 max_hold_bars)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.composer_framework.signal_source import (
    InsufficientSourceDataError, SignalSource, SourceContext)
from app.composer_framework.sources.rsi_threshold_source import (
    apply_entry_placebo)


def band_z(close: pd.Series, period: int) -> pd.Series:
    """표본이 아니라 **모집단** 표준편차(ddof=0). 볼린저의 관례가 이쪽이고,
    ddof 를 바꾸면 같은 sigma 가 다른 문턱이 된다."""
    ma = close.rolling(period).mean()
    sd = close.rolling(period).std(ddof=0)
    return (close - ma) / sd.replace(0.0, np.nan)


class BandExtremeSource(SignalSource):
    name = "band_extreme"
    feature_prefix = "band_"
    requires = ("ohlcv_eval",)

    def __init__(self, period: int = 20, sigma: float = 2.0,
                 side: str = "long", placebo: str = "",
                 placebo_seed: int = 0, entry_mode: str = "cross_back") -> None:
        if side not in ("long", "short"):
            raise ValueError(f"side 는 long|short — 받은 값 {side!r}")
        if not (sigma > 0.0):
            raise ValueError(f"sigma 는 양수 — {sigma!r}")
        if period < 2:
            raise ValueError(f"period 는 2 이상 — {period!r}")
        if placebo not in ("", "rotate", "random"):
            raise ValueError(f"placebo 는 ''|rotate|random — {placebo!r}")
        # level      : 밴드 밖에 있는 **모든 봉**에서 발화
        # cross_back : 밴드 **안으로 되돌아 들어오는 봉**에서만 발화
        #
        # ⚠ 기본값이 cross_back 이다 (RSI 트랙과 반대)
        #   level 은 떨어지는 내내 발화해 급락 한복판에 진입한다. 실측
        #   슬리피지가 155.9bp → 57.1bp 로 3분의 1이 됐고, 손절을 빼면
        #   8.6bp 까지 내려갔다. 이 신호원은 그 골격에 꽂을 목적으로 만든다.
        if entry_mode not in ("level", "cross_back"):
            raise ValueError(f"entry_mode 는 level|cross_back — {entry_mode!r}")
        self.period = int(period)
        self.sigma = float(sigma)
        self.side = side
        self.placebo = placebo
        self.placebo_seed = int(placebo_seed)
        self.entry_mode = entry_mode

    def _apply_placebo(self, sig: pd.Series) -> pd.Series:
        return apply_entry_placebo(sig, self.placebo, self.placebo_seed)

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        ohlc = ctx.ohlcv_eval
        if ohlc is None or "close" not in ohlc.columns:
            raise InsufficientSourceDataError(
                f"{ctx.symbol}: ohlcv_eval 에 close 가 없다")

        df = ohlc[["close"]].astype(float).copy()
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        df = df[~df.index.duplicated(keep="last")]
        need = self.period * 5
        if len(df) < need:
            raise InsufficientSourceDataError(
                f"{ctx.symbol}: 봉 {len(df)}개 < 필요 {need}개 "
                f"(볼린저 {self.period} 워밍업)")

        z = band_z(df["close"], self.period)
        # `inside` = 밴드 **밖**(극단 구간)에 있는가. 방향은 여기서만 갈린다.
        if self.side == "long":
            inside = (z <= -self.sigma).fillna(False)
            val = 1.0
        else:
            inside = (z >= self.sigma).fillna(False)
            val = -1.0

        if self.entry_mode == "level":
            hit = inside
        else:
            # 되돌아 나오는 봉 — 직전 봉은 밴드 밖, 이번 봉은 밴드 안.
            # t-1 과 t 만 본다(미래 없음). 체결은 커널이 t+1 시가에 한다.
            hit = (~inside) & inside.shift(1).fillna(False)

        sig = pd.Series(0.0, index=df.index)
        sig.loc[hit] = val
        sig = self._apply_placebo(sig)

        eval_idx = pd.to_datetime(ctx.ohlcv_eval.index)
        out = pd.DataFrame(index=eval_idx)
        out["band_signal"] = sig.reindex(eval_idx).fillna(0.0).astype(float)
        out["band_z"] = z.reindex(eval_idx).astype(float)
        return out
