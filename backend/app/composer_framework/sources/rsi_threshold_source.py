"""RsiThresholdSource — RSI 문턱 진입 신호. 익절·손절은 정책이 맡는다.

왜 소스로 만드나
    RSI + 익절 + 손절은 손익 구현체를 새로 짤 이유가 전혀 없는 단순 규칙이다.
    **정본 커널(`GenericBacktester.run_rule_based`)**에 그대로 흘려보낼 수
    있도록 신호만 내는 소스로 만든다. 이 저장소에서 손익 구현체 6개 중 4개가
    오염됐던 원인이 "그때그때 백테스터를 새로 짠 것" 이었다.

규칙 (Wilder RSI, 기본 14)
    롱 : RSI <= entry_threshold           (과매도 되돌림)
    숏 : RSI >= (100 - entry_threshold)   (과매수 되돌림)
    `side` 로 방향을 고른다. 양쪽을 다 내면 대조가 성립하지 않는다 —
    **같은 문턱의 거울**을 따로 돌려 비교해야 한다 (교훈 #91).

⚠ 미래참조 없음
    RSI 는 t 시점 종가까지만 쓴다. 체결은 커널이 `signal_lag_bars=1` 로
    다음 봉 시가에 낸다. 소스에서 추가로 밀지 않는다 — 두 번 밀면 규약이
    어긋난다 (교훈 #90: 소스가 이미 시점보정 하는지 먼저 읽어라).

⚠ 데이터 결손은 **0 신호로 감추지 않는다**
    봉이 모자라면 `InsufficientSourceDataError` 를 낸다. 조용한 0 신호는
    "죽은 전략"과 "쉬는 전략"을 구별 못 하게 만든다.

출력 (prefix `rsi_`)
    rsi_signal — {-1.0, 0.0, +1.0}
    rsi_value  — RSI 원값 (디버그·진단용)

조합: `PassthroughComposer`(feature_col=rsi_signal) +
      `LongShortThresholdPolicy`(entry_threshold=0.5, sl_pct, tp_pct,
                                 max_hold_bars)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.composer_framework.signal_source import (
    InsufficientSourceDataError, SignalSource, SourceContext)


def wilder_rsi(close: pd.Series, period: int) -> pd.Series:
    """Wilder 평활 RSI. 단순이동평균판(`rolling.mean()`)과 값이 다르다.

    Wilder 는 `alpha = 1/period` 인 지수평활이다. 거래소·차트 도구가 쓰는
    기본형이 이쪽이므로 여기에 맞춘다.
    """
    d = close.diff()
    up = d.clip(lower=0.0)
    dn = (-d).clip(lower=0.0)
    ru = up.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rd = dn.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = ru / rd.replace(0.0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    # 하락이 전혀 없던 구간은 rs=inf → RSI 100. 상승이 없으면 RSI 0.
    rsi = rsi.where(rd != 0.0, 100.0)
    rsi = rsi.where(~((ru == 0.0) & (rd == 0.0)), 50.0)
    return rsi


class RsiThresholdSource(SignalSource):
    name = "rsi_threshold"
    feature_prefix = "rsi_"
    requires = ("ohlcv_eval",)

    def __init__(self, period: int = 14, entry_threshold: float = 30.0,
                 side: str = "long", placebo: str = "",
                 placebo_seed: int = 0) -> None:
        if side not in ("long", "short"):
            raise ValueError(f"side 는 long|short — 받은 값 {side!r}")
        if not (0.0 < entry_threshold < 100.0):
            raise ValueError(f"entry_threshold 는 (0,100) — {entry_threshold!r}")
        if period < 2:
            raise ValueError(f"period 는 2 이상 — {period!r}")
        if placebo not in ("", "rotate", "random"):
            raise ValueError(f"placebo 는 ''|rotate|random — {placebo!r}")
        self.period = int(period)
        self.entry_threshold = float(entry_threshold)
        self.side = side
        self.placebo = placebo
        self.placebo_seed = int(placebo_seed)

    def _apply_placebo(self, sig: pd.Series) -> pd.Series:
        """진입 대조군.

        rotate — 신호를 **과거 쪽에서** 끌어온다(`np.roll(k>0)` 은 i 에 i-k 의
                 값을 놓는다). 진입 **횟수와 뭉침 구조가 실측과 동일**하고
                 가격 경로와의 연결만 끊긴다. 그래서 "규칙(익절·손절)이 번 것"과
                 "RSI 가 번 것"을 가른다.
                 ⚠ 원형이라 앞쪽 k 개는 **끝(미래)** 에서 온다 → 그 구간은 0 으로
                   지운다. 안 지우면 위약이 미래를 보게 된다.
        random — 같은 개수를 균등 무작위 시점에 뿌린다. 뭉침이 사라지므로
                 rotate 보다 약한 대조지만, 뭉침 자체의 효과를 본다.
        """
        n = len(sig)
        if n < 10 or self.placebo == "":
            return sig
        rng = np.random.default_rng(self.placebo_seed)
        if self.placebo == "rotate":
            # ⚠ 회전량은 5~20% 로 제한한다. 크게 돌리면 앞쪽을 그만큼 지워야
            #   해서 진입 횟수가 무너진다(실측 173→67). 5~20% 면 1시간봉에서
            #   수개월치라 가격 경로와의 연결을 끊기엔 충분하다.
            k = int(rng.integers(max(n // 20, 1), max(n // 5, 2)))
            out = pd.Series(np.roll(sig.to_numpy(), k), index=sig.index)
            out.iloc[:k] = 0.0
            return out
        nz = sig.to_numpy()
        cnt = int((nz != 0).sum())
        val = float(nz[nz != 0][0]) if cnt else 0.0
        out = np.zeros(n)
        if cnt:
            out[rng.choice(n, size=min(cnt, n), replace=False)] = val
        return pd.Series(out, index=sig.index)

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
                f"(RSI {self.period} 워밍업)")

        rsi = wilder_rsi(df["close"], self.period)
        if self.side == "long":
            hit = rsi <= self.entry_threshold
            val = 1.0
        else:
            hit = rsi >= (100.0 - self.entry_threshold)
            val = -1.0

        sig = pd.Series(0.0, index=df.index)
        sig.loc[hit.fillna(False)] = val
        sig = self._apply_placebo(sig)

        eval_idx = pd.to_datetime(ctx.ohlcv_eval.index)
        out = pd.DataFrame(index=eval_idx)
        out["rsi_signal"] = sig.reindex(eval_idx).fillna(0.0).astype(float)
        out["rsi_value"] = rsi.reindex(eval_idx).astype(float)
        return out
