"""BinanceLifecycleDecaySource — constant -1 signal for the lifecycle short paradigm.

Hypothesis (paradigm-architect R-4 PASS on 2026-05-13, see
`research_track/INDEX.json`):
  Newly listed Binance Futures USDT perpetuals systematically decay 20-30%
  in the first 30 days from Day-1 close. n=167 cohort, median +21.6%/trade,
  win 58.1%, permutation σ=6.8 / p=0.000, bootstrap median CI [+3.3%, +31.5%].
  Refined R-2 (paradigm `listing_volume_cliff`): when filtered by
  vol_cliff < 0.30 (Day 7-14 vol < 30% of Day 1), median rises to +34.9%
  win 69%.

This source is paired with a per-listing PaperSession created by the
listing-spawner CLI. Once created and run for the first time, the
constant -1 signal forces an immediate SHORT entry via
PassthroughComposer + LongShortThresholdPolicy. Subsequent daily cycles
are managed by the policy's in-position branch (SL via orchestrator's
forced_exit price check, time-stop at max_hold_bars=30).

Output (single signal column, prefix `bnld_`):
  bnld_signal — constant -1.0 (forces SHORT). NaN at index ends only if
                ohlcv_eval is empty (caller's responsibility).

Pair with:
  composer: passthrough (feature_col=bnld_signal, scale=1.0)
  policy:   long_short_threshold (entry_threshold=0.5, sl_pct=0.50,
            tp_pct=1.0, max_hold_bars=30)
  config:   eval_freq_minutes=1440, forward_bars=30

No runtime data dependency beyond ohlcv_eval (which paper_session_cli
always provides).

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


class BinanceLifecycleDecaySource(SignalSource):
    name = "bn_lifecycle_decay"
    feature_prefix = "bnld_"
    requires = ("ohlcv_eval",)

    def __init__(self, *, listing_date: str | None = None,
                 max_age_days: int = 30,
                 entry_window_days: int = 3,
                 entry_start_hours: int = 0) -> None:
        self.listing_date = listing_date
        self.max_age_days = int(max_age_days)
        self.entry_window_days = int(entry_window_days)
        # ⚠ 진입 **시작** 시각(상장 후 시간). 기본 0 = 종전과 동일.
        #   `entry_window_days` 는 창을 **닫기만** 해서, 1시간봉에서는 창이
        #   상장 즉시 열려 **상장가에 진입**한다. 그건 이미 기각된 변형이다
        #   (교훈 #90: 251 코호트 평균 +5.15% → -0.37% 반전).
        #
        #   왜 24시간을 기다리나 — 실측 487상장:
        #     상장가 → +24h  중앙값 **-1.1%** (오른 경우 46%)
        #     Day-1 최고점   중앙값 **+11.5%** · p90 **+63.6%**
        #   더 비싸게 팔려는 게 아니라 **초기 급등에 손절당하지 않으려는** 것이다.
        self.entry_start_hours = int(entry_start_hours)

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        idx = pd.to_datetime(ctx.ohlcv_eval.index)
        out = pd.DataFrame(index=idx)
        # Constant short signal. Once policy enters at first cycle, subsequent
        # cycles' signal value is ignored (policy.in_position branch).
        out["bnld_signal"] = -1.0
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
            _entry_start = _t0 + pd.Timedelta(hours=self.entry_start_hours)
            _entry_end = _t0 + pd.Timedelta(days=self.entry_window_days)
            _all_end = _t0 + pd.Timedelta(days=self.max_age_days)
            _c = "bnld_signal"
            # 창 **밖**(이르거나 늦은)의 진입 신호를 죽인다
            out.loc[(out.index < _entry_start) & (out[_c] < 0), _c] = 0.0
            out.loc[(out.index > _entry_end) & (out[_c] < 0), _c] = 0.0
            out.loc[out.index > _all_end, _c] = 0.0
        return out
