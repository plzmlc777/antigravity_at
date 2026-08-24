"""VolumeCapitulationSource — 거래량 폭증을 **동반한** 급락의 되돌림.

왜 이 신호원인가 (2026-08-22)
    ① 중복도 검사에서 이 축은 **유일하게 어느 지표와도 안 뭉쳤다**
       (최대 자카드 0.337 · RSI와 0.258). 지수평활 뭉치(RSI·MFI·켈트너)에도,
       고정창 뭉치(Stoch·%R·볼린저·CCI)에도 속하지 않는다.
       가격 밖 정보(거래량)를 쓰기 때문이다.
    ② 볼린저가 실패한 이유가 진단됐기 때문이다. 볼린저는 평균 대비 편차만
       크면 발화해 **평범한 하락 한 다리**를 잡았고, 위약과의 차이가
       −0.001 이었다. RSI가 버는 이유는 지수평활이라 **한 방향 매도의
       누적(항복)** 을 요구해서다. 거래량 폭증 요구는 항복을 **직접**
       요구한다 — 논리적으로 다음 순서다.

규칙
    vol_z  = (volume − SMA(volume, vol_window)) / STD(volume, vol_window)
    ret_k  = close.pct_change(ret_bars)
    롱 : vol_z >= vol_z_min  그리고  ret_k <= ret_threshold   (ret_threshold < 0)
    숏 : vol_z >= vol_z_min  그리고  ret_k >= −ret_threshold
    거래량 조건은 **양방향 동일**하다 — 폭증에는 방향이 없다.
    가격 조건만 거울로 뒤집는다 (교훈 #91).

⚠ `side` 는 **방아쇠**(어떤 가격 조건), `direction` 은 **포지션**이다 — 둘은 다르다
    2026-08-22 실측: 급락 후 되돌림 매수가 **위약보다 1.704%/거래 나빴다**
    (12종목·355거래). 위약과 차이가 0 이면 정보가 없는 것이지만, 위약보다
    꾸준히 **나쁘면 신호가 뭔가를 맞히고 있고 방향만 뒤집힌** 것이다
    (교훈 #39 sub-B). 그래서 방아쇠와 포지션을 갈라 파라미터로 둔다.
      reversion    — 급락 후 **매수** (되돌림 가설)
      continuation — 급락 후 **매도** (추세지속 가설)
    파라미터로 두지 않고 부호를 손으로 뒤집으면, 나중에 어느 판본이었는지
    산출물만 봐서는 못 가린다.

⚠ 미래참조 없음
    rolling·pct_change 는 t 시점까지만 쓴다. 체결은 커널이
    `signal_lag_bars=1` 로 다음 봉 시가에 낸다 (교훈 #90).

⚠ 데이터 결손은 0 신호로 감추지 않는다 — `InsufficientSourceDataError`.

⚠ 위약은 공용 구현 하나 (`apply_entry_placebo`).

출력 (prefix `volcap_`)
    volcap_signal — {-1.0, 0.0, +1.0}
    volcap_volz   — 거래량 z (진단용)
    volcap_ret    — ret_k (진단용)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.composer_framework.signal_source import (
    InsufficientSourceDataError, SignalSource, SourceContext)
from app.composer_framework.sources.rsi_threshold_source import (
    apply_entry_placebo)


def volume_z(volume: pd.Series, window: int) -> pd.Series:
    """모집단 표준편차(ddof=0). 거래량은 로그정규에 가까워 z가 우측으로
    길게 늘어진다 — 문턱 3~4가 흔한 이유다."""
    ma = volume.rolling(window).mean()
    sd = volume.rolling(window).std(ddof=0)
    return (volume - ma) / sd.replace(0.0, np.nan)


class VolumeCapitulationSource(SignalSource):
    name = "volume_capitulation"
    feature_prefix = "volcap_"
    requires = ("ohlcv_eval",)

    def __init__(self, vol_window: int = 96, vol_z_min: float = 3.0,
                 ret_bars: int = 5, ret_threshold: float = -0.03,
                 side: str = "long", direction: str = "reversion",
                 placebo: str = "",
                 placebo_seed: int = 0, entry_mode: str = "cross_back") -> None:
        if side not in ("long", "short"):
            raise ValueError(f"side 는 long|short — 받은 값 {side!r}")
        if vol_window < 10:
            raise ValueError(f"vol_window 는 10 이상 — {vol_window!r}")
        if not (vol_z_min > 0.0):
            raise ValueError(f"vol_z_min 은 양수 — {vol_z_min!r}")
        if ret_bars < 1:
            raise ValueError(f"ret_bars 는 1 이상 — {ret_bars!r}")
        # ⚠ 롱 기준으로 **음수**만 받는다. 부호를 실수로 뒤집으면 '급락 진입'이
        #   조용히 '급등 진입'이 된다 — 산출물만 봐서는 안 보인다.
        if not (ret_threshold < 0.0):
            raise ValueError(f"ret_threshold 는 음수(롱 기준 급락) — "
                             f"{ret_threshold!r}")
        if direction not in ("reversion", "continuation"):
            raise ValueError(f"direction 은 reversion|continuation — {direction!r}")
        if placebo not in ("", "rotate", "random"):
            raise ValueError(f"placebo 는 ''|rotate|random — {placebo!r}")
        if entry_mode not in ("level", "cross_back"):
            raise ValueError(f"entry_mode 는 level|cross_back — {entry_mode!r}")
        self.vol_window = int(vol_window)
        self.vol_z_min = float(vol_z_min)
        self.ret_bars = int(ret_bars)
        self.ret_threshold = float(ret_threshold)
        self.side = side
        self.direction = direction
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
        if "volume" not in ohlc.columns:
            raise InsufficientSourceDataError(
                f"{ctx.symbol}: ohlcv_eval 에 volume 이 없다 — 이 신호원은 "
                f"가격만으로는 성립하지 않는다")

        df = ohlc[["close", "volume"]].astype(float).copy()
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        df = df[~df.index.duplicated(keep="last")]
        need = (self.vol_window + self.ret_bars) * 3
        if len(df) < need:
            raise InsufficientSourceDataError(
                f"{ctx.symbol}: 봉 {len(df)}개 < 필요 {need}개 "
                f"(거래량 창 {self.vol_window} 워밍업)")

        vz = volume_z(df["volume"], self.vol_window)
        rk = df["close"].pct_change(self.ret_bars)
        burst = (vz >= self.vol_z_min).fillna(False)
        # 거래량 조건은 양방향 공통. 가격 조건만 거울로 뒤집는다.
        if self.side == "long":
            inside = burst & (rk <= self.ret_threshold).fillna(False)
            val = 1.0                    # 급락 → 매수 (되돌림)
        else:
            inside = burst & (rk >= -self.ret_threshold).fillna(False)
            val = -1.0                   # 급등 → 매도 (되돌림)
        if self.direction == "continuation":
            val = -val                   # 방아쇠는 그대로, 포지션만 뒤집는다

        if self.entry_mode == "level":
            hit = inside
        else:
            # 되돌아 나오는 봉 — 직전 봉은 항복 구간 안, 이번 봉은 밖.
            hit = (~inside) & inside.shift(1).fillna(False)

        sig = pd.Series(0.0, index=df.index)
        sig.loc[hit] = val
        sig = self._apply_placebo(sig)

        eval_idx = pd.to_datetime(ctx.ohlcv_eval.index)
        out = pd.DataFrame(index=eval_idx)
        out["volcap_signal"] = sig.reindex(eval_idx).fillna(0.0).astype(float)
        out["volcap_volz"] = vz.reindex(eval_idx).astype(float)
        out["volcap_ret"] = rk.reindex(eval_idx).astype(float)
        return out
