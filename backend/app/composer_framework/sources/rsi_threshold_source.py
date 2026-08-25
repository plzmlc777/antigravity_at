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
                 placebo_seed: int = 0, entry_mode: str = "level",
                 min_atr_pct: float = 0.0, max_drop_pct: float = 0.0,
                 min_vol_mult: float = 0.0) -> None:
        if side not in ("long", "short"):
            raise ValueError(f"side 는 long|short — 받은 값 {side!r}")
        if not (0.0 < entry_threshold < 100.0):
            raise ValueError(f"entry_threshold 는 (0,100) — {entry_threshold!r}")
        if period < 2:
            raise ValueError(f"period 는 2 이상 — {period!r}")
        if placebo not in ("", "rotate", "random"):
            raise ValueError(f"placebo 는 ''|rotate|random — {placebo!r}")
        # level      : 조건 안에 있는 **모든 봉**에서 발화(기존 동작)
        # cross_back : 조건 밖으로 **되돌아 나오는 봉**에서만 발화
        #
        # ⚠ 왜 cross_back 이 필요한가 (2026-08-21)
        #   level 은 떨어지는 내내 발화해서 **급락 한복판에 진입**한다.
        #   실측: 손절 슬리피지 최악 15건 중 13건이 `2025-10-10 21:20`
        #   한 시각이었다 — 그 분에 물려 있었기 때문이다.
        #   되돌아 나올 때 사면 그 순간을 통째로 피한다.
        #   대가는 진입가가 높아지는 것 — 거래당 익절 %는 그대로지만
        #   **거기서 익절까지 갈 확률**이 달라진다. 그게 검정할 지점이다.
        if entry_mode not in ("level", "cross_back"):
            raise ValueError(f"entry_mode 는 level|cross_back — {entry_mode!r}")
        self.period = int(period)
        self.entry_threshold = float(entry_threshold)
        self.side = side
        self.placebo = placebo
        self.placebo_seed = int(placebo_seed)
        self.entry_mode = entry_mode
        # ── 진입 게이트 (2026-08-25) ──────────────────────────────
        #   1,725거래를 거래 단위로 갈라 찾은 셋. **상위 5일을 뺀** 표본에서
        #   날짜 묶음 위약을 통과했고(p 0.001), 앞→뒤 절반 확인도 4/4 였다.
        #   ⚠ 상위 5일을 뺀 이유 — 2025-10-10 하루가 익절의 68% 였다.
        #     그 날을 표시하는 변수는 무엇이든 예측력이 있어 보인다
        #     (`hour` 가 70.3%p 를 갈랐다). 빼야 진짜 특성이 남는다.
        #
        #   min_atr_pct  : 30분봉 ATR(진입가 대비 %) 하한. 실측 Q1(<0.98%)
        #                  익절률 6.1% 로 **손익분기 7.8% 미달**. 0=끔
        #   max_drop_pct : 직전 하락 폭 상한(음수). -12 면 12% 이상 떨어진
        #                  것만. 실측 Q1(-20%↓) 18.4% vs Q5(-5.6%↑) 5.6%. 0=끔
        #   min_vol_mult : 거래량 배수 하한. 실측 Q5(15배↑) 20.1%. 0=끔
        if min_atr_pct < 0 or min_vol_mult < 0:
            raise ValueError("min_atr_pct·min_vol_mult 는 0 이상")
        if max_drop_pct > 0:
            raise ValueError(f"max_drop_pct 는 0 이하(하락은 음수) — {max_drop_pct!r}")
        self.min_atr_pct = float(min_atr_pct)
        self.max_drop_pct = float(max_drop_pct)
        self.min_vol_mult = float(min_vol_mult)

    @property
    def gated(self) -> bool:
        return bool(self.min_atr_pct or self.max_drop_pct or self.min_vol_mult)

    def _apply_placebo(self, sig: pd.Series) -> pd.Series:
        """진입 대조군. 구현은 `apply_entry_placebo` **한 곳**뿐이다 —
        신호원마다 복사하면 위약이 소스마다 달라진다."""
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
                f"(RSI {self.period} 워밍업)")

        rsi = wilder_rsi(df["close"], self.period)
        # `inside` = 과열 구간 안에 있는가. 방향은 여기서만 갈린다.
        if self.side == "long":
            inside = (rsi <= self.entry_threshold).fillna(False)
            val = 1.0
        else:
            inside = (rsi >= (100.0 - self.entry_threshold)).fillna(False)
            val = -1.0

        if self.entry_mode == "level":
            hit = inside
        else:
            # 되돌아 나오는 봉 — 직전 봉은 구간 안, 이번 봉은 구간 밖.
            # t-1 과 t 만 본다(미래 없음). 체결은 커널이 t+1 시가에 한다.
            hit = (~inside) & inside.shift(1).fillna(False)

        if self.gated:
            hit = hit & self._gate_mask(ohlc, rsi, df.index)

        sig = pd.Series(0.0, index=df.index)
        sig.loc[hit] = val
        sig = self._apply_placebo(sig)

        eval_idx = pd.to_datetime(ctx.ohlcv_eval.index)
        out = pd.DataFrame(index=eval_idx)
        out["rsi_signal"] = sig.reindex(eval_idx).fillna(0.0).astype(float)
        out["rsi_value"] = rsi.reindex(eval_idx).astype(float)
        return out

    # ── 진입 게이트 ────────────────────────────────────────────
    RECOVER = 30.0          # 하락 구간의 끝 — RSI 가 여기를 넘으면 구간이 아니다

    def _gate_mask(self, ohlc, rsi: pd.Series, idx) -> pd.Series:
        """세 조건을 모두 만족하는 봉만 True.

        ⚠ 전부 **그 봉 종가까지의 정보**로만 만든다. 체결은 커널이 다음 봉
          시가에 하므로 미래참조가 없다(교훈 #90 — 두 번 밀지 않는다).
        """
        need = [c for c in ("high", "low", "close", "volume")
                if c not in ohlc.columns]
        if need:
            raise InsufficientSourceDataError(
                f"게이트에 필요한 컬럼이 없다: {need}")
        o = ohlc.astype(float).copy()
        o.index = pd.to_datetime(o.index)
        o = o.sort_index()
        o = o[~o.index.duplicated(keep="last")].reindex(idx)
        c, h, l, v = o["close"], o["high"], o["low"], o["volume"]

        m = pd.Series(True, index=idx)

        if self.min_atr_pct > 0:
            pc = c.shift(1)
            tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()],
                           axis=1).max(axis=1)
            atr = tr.ewm(alpha=1.0 / 14, adjust=False).mean() / c * 100.0
            m &= (atr >= self.min_atr_pct).fillna(False)

        if self.max_drop_pct < 0 or self.min_vol_mult > 0:
            below = (rsi <= self.RECOVER).fillna(False).to_numpy()
            cv = c.to_numpy(); vv = v.to_numpy()
            n = len(cv)
            drop = np.full(n, np.nan)
            vmul = np.full(n, np.nan)
            start = 0
            for i in range(n):
                if not below[i]:
                    start = i + 1
                    continue
                # 이번 하락 구간은 [start, i] — 미래를 안 본다
                st = start
                peak = cv[max(0, st - 1)]
                seg = cv[st:i + 1]
                if peak > 0 and len(seg):
                    drop[i] = 100.0 * (seg.min() / peak - 1.0)
                base = vv[max(0, st - 100):st]
                b = base.mean() if len(base) else np.nan
                if b and b > 0:
                    vmul[i] = vv[st:i + 1].mean() / b
            if self.max_drop_pct < 0:
                m &= pd.Series(drop <= self.max_drop_pct, index=idx).fillna(False)
            if self.min_vol_mult > 0:
                m &= pd.Series(vmul >= self.min_vol_mult, index=idx).fillna(False)
        return m


def apply_entry_placebo(sig: pd.Series, placebo: str, seed: int) -> pd.Series:
    """진입 대조군 — **모든 신호원이 이 구현 하나를 쓴다** (2026-08-22 공용화).

    rotate — 신호를 **과거 쪽에서** 끌어온다(`np.roll(k>0)` 은 i 에 i-k 의
             값을 놓는다). 진입 **횟수와 뭉침 구조가 실측과 동일**하고
             가격 경로와의 연결만 끊긴다. 그래서 "규칙(익절·손절)이 번 것"과
             "지표가 번 것"을 가른다.
             ⚠ 원형이라 앞쪽 k 개는 **끝(미래)** 에서 온다 → 그 구간은 0 으로
               지운다. 안 지우면 위약이 미래를 보게 된다.
    random — 같은 개수를 균등 무작위 시점에 뿌린다. 뭉침이 사라지므로
             rotate 보다 약한 대조지만, 뭉침 자체의 효과를 본다.
    """
    n = len(sig)
    if n < 10 or placebo == "":
        return sig
    rng = np.random.default_rng(seed)
    if placebo == "rotate":
        # ⚠ 회전량은 5~20% 로 제한한다. 크게 돌리면 앞쪽을 그만큼 지워야
        #   해서 진입 횟수가 무너진다(실측 173→67).
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
