"""BinanceLifecycleDecayBearSkipSource — regime-gated lifecycle short signal.

R-3 regime analysis (`runs/research_track/lifecycle_phase/r3__metrics.json`,
n=167 cohort) showed strong outcome divergence by BTC 30d pre-listing regime:

  BEAR (BTC_30d_pre <= -0.05): n=38, median **-50.08%**, win 42.1% — catastrophic
  NEUTRAL (-0.05..+0.05):      n=78, median +28.21%, win 60.3%
  BULL (>= +0.05):             n=51, median +30.24%, win 66.7%

Strategy-vs-BTC correlation was -0.241 (counter-correlated), confirming the
short side is fundamentally betting AGAINST BTC's near-term direction.

This source emits the standard -1.0 short signal in NEUTRAL/BULL regimes and
suppresses the signal (0.0) in BEAR regimes. The regime decision is FROZEN at
spawn time (the `btc_30d_pre_ret` value is supplied by the spawner from a
real-time BTC ohlcv query at listing date); the source itself does not
re-query BTC at runtime — keeping it cheap and consistent across cycles.

Output (single signal column, prefix `bnldbs_`):
  bnldbs_signal — -1.0 (short) if btc_30d_pre_ret > bear_threshold, else 0.0
                  (no entry). NaN at index ends only if ohlcv_eval is empty.

Pair with:
  composer: passthrough (feature_col=bnldbs_signal, scale=1.0)
  policy:   long_short_threshold (entry_threshold=0.5, sl_pct=0.50,
            tp_pct=1.0, max_hold_bars=30)
  config:   eval_freq_minutes=1440, forward_bars=30

Spawner sets `btc_30d_pre_ret` once at session creation; the value persists
in the session spec JSON. No runtime data dependency beyond ohlcv_eval.

재진입 차단 (2026-08-12 수정)
  이 소스는 신호를 **영원히** 내보냈다. 원래 주석은 "정책이 첫 사이클에 진입하면
  이후 신호값은 무시된다(policy.in_position 분기)" 라고 적었는데, 그건 **포지션이
  절대 안 닫힐 때만** 참이다. 익절·손절·시간청산으로 나가는 순간 정책은 flat 이
  되고 신호는 그대로라 **즉시 재진입한다.**

  실측(2026-08-12): DATAIPUSDT 는 상장 후 한 달에 네 번 진입했다. active 세션
  67개 중 포지션 보유 46개가 전부 원래 창을 넘긴 재진입분이었다. 설계는
  "상장 사건당 Day-1 숏 한 번" 인데 반복 모멘텀 전략이 돼 있었다.

  실계좌 트랙은 2026-07-27 에 드라이버 age>=31d 차단으로 고쳤으나 **페이퍼
  소스는 안 고쳤다.** 여기서 소스 층에 같은 차단을 넣는다.

  listing_date 가 주어지면 그 날 + max_age_days 까지만 신호를 내고 이후는 0.0
  (진입 임계 미달 → 신규 진입 없음. 보유 중이면 조기청산 임계 0.5 에도 못
  미치므로 기존 포지션엔 영향 없음). listing_date 가 없으면 종전 동작 유지.
"""
from __future__ import annotations

import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext


class BinanceLifecycleDecayBearSkipSource(SignalSource):
    name = "bn_lifecycle_decay_bear_skip"
    feature_prefix = "bnldbs_"
    requires = ("ohlcv_eval",)

    def __init__(
        self,
        *,
        btc_30d_pre_ret: float,
        bear_threshold: float = -0.05,
        listing_date: str | None = None,
        max_age_days: int = 30,
        entry_window_days: int = 3,
    ) -> None:
        self.listing_date = listing_date
        self.max_age_days = int(max_age_days)
        self.entry_window_days = int(entry_window_days)
        self.btc_30d_pre_ret = float(btc_30d_pre_ret)
        self.bear_threshold = float(bear_threshold)

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        idx = pd.to_datetime(ctx.ohlcv_eval.index)
        out = pd.DataFrame(index=idx)
        is_bear = self.btc_30d_pre_ret <= self.bear_threshold
        out["bnldbs_signal"] = 0.0 if is_bear else -1.0
        # 재진입 차단 — **진입 신호만** 창을 닫는다.
        #
        # max_age_days(30) 만으로는 부족하다. 창 안에서도 익절로 나가면 신호가
        # 아직 -1.0 이라 다시 들어간다 (DATAIPUSDT 는 30일 안에 네 번 진입했다).
        # 패러다임은 "상장 Day-1 종가 숏 **한 번**" 이므로 진입 신호는 상장
        # 직후 며칠만 열려 있으면 된다. 일봉 평가(eval_freq 1440)에서 entry_window_days
        # 만큼이면 첫 사이클에 반드시 발화한다.
        #
        # **음수(진입)만 0 으로 만들고 양수(조기청산)는 남긴다.** 조기청산 신호는
        # Day 7/14 에 나오므로 진입 창을 짧게 닫아도 살아 있어야 한다.
        if getattr(self, "listing_date", None):
            _t0 = pd.Timestamp(self.listing_date)
            _entry_end = _t0 + pd.Timedelta(days=self.entry_window_days)
            _all_end = _t0 + pd.Timedelta(days=self.max_age_days)
            _c = "bnldbs_signal"
            out.loc[(out.index > _entry_end) & (out[_c] < 0), _c] = 0.0
            out.loc[out.index > _all_end, _c] = 0.0
        return out
