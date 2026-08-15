"""BinanceLifecycleDecayEarlyExitSource — Day N vol-cliff gated short signal.

Variant of `bn_lifecycle_decay` that adds an early-exit signal when the
observed vol_cliff at a chosen check day exceeds a "decay invalidated"
threshold. The base paradigm (lifecycle_pump_decay R-4 PASS) is short Day 1
close, hold to Day 30 close. The amplifier (listing_volume_cliff R-2 PASS)
showed vol_cliff < 0.30 strongly improves outcomes; the inverse — vol_cliff
high → pump continuing → not abandoned — motivates this early exit.

Signal column `bnldex_signal` per cycle bar:
  - cycle_pos < check_day:                          -1.0  (enter / continue short)
  - cycle_pos >= check_day, vol_cliff < hi_thresh:  -1.0  (decay confirmed, hold)
  - cycle_pos >= check_day, vol_cliff >= hi_thresh: +1.0  (decay invalidated, EARLY EXIT — persists across subsequent cycles so a missed cron tick on the exact check_day doesn't strand the session)

vol_cliff computation:
  - check_day=14 (default, MATCHES R-2): vol_cliff = mean(vol[7:14]) / vol[0]
    Both numerator (7 daily bars Days 8-14) and denominator (Day 1) are
    OBSERVED at Day 14 close — the EXACT same metric R-2 retrospective
    measured. Highest signal fidelity.
  - check_day=7 (aggressive partial): vol_cliff_partial = mean(vol[1:7]) / vol[0]
    Uses 6 observed daily bars (Days 2-7) — earlier detection but with a
    different (and weaker, per R-2 forecaster R²=0.035) signal.

Pair with:
  composer: passthrough (feature_col=bnldex_signal, scale=1.0)
  policy:   lifecycle_decay_early_exit (entry_threshold=0.5, sl_pct=0.50,
            exit_on_invalidation=True, max_hold_bars=30)
  config:   eval_freq_minutes=1440, forward_bars=30

No runtime data dependency beyond ohlcv_eval.

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

import numpy as np
import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext


class BinanceLifecycleDecayEarlyExitSource(SignalSource):
    name = "bn_lifecycle_decay_early_exit"
    feature_prefix = "bnldex_"
    requires = ("ohlcv_eval",)

    def __init__(
        self,
        *,
        check_day: int = 14,
        vol_cliff_hi_threshold: float = 0.40,
        listing_date: str | None = None,
        max_age_days: int = 30,
        entry_window_days: int = 3,
    ) -> None:
        self.listing_date = listing_date
        self.max_age_days = int(max_age_days)
        self.entry_window_days = int(entry_window_days)
        self.check_day = int(check_day)
        self.vol_cliff_hi_threshold = float(vol_cliff_hi_threshold)
        if self.check_day not in (7, 14):
            # Permitted but warn at runtime via signal value semantics — both
            # branches degrade to "partial" when check_day < 14.
            pass

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        df = ctx.ohlcv_eval
        idx = pd.to_datetime(df.index)
        out = pd.DataFrame(index=idx)
        out["bnldex_signal"] = -1.0  # default: continue short

        vols_raw = df["volume"].astype(float).values

        # ── 해상도 무관화 (2026-08-15) ───────────────────────────────────
        # 종전에는 `Day N = iloc[N-1]` 로 **봉 개수**를 세었다. 일봉에서는
        # 맞지만 1시간봉을 주면 d7 이 **7시간**, d14 가 **14시간**이 되어
        # 조용히 다른 전략이 된다.
        #
        # `eval_freq_minutes` 로 하루치 봉 수를 구해 **일 단위로 접는다.**
        # 일봉(1440)이면 bars_per_day=1 이라 `vols_raw` 그대로 —
        # **기존 동작이 바뀌지 않는다**(골든 재생으로 확인할 것).
        #
        # ⚠ 시각 기준으로 다시 짜지 않는 이유: `ohlcv_daily` 는 상장일
        #   부분봉을 제외하므로 일봉에서는 `iloc[0]` 이 이미 상장+1일이다.
        #   시각으로 바꾸면 Day 번호가 하루 밀려 **라이브 동작이 바뀐다.**
        bars_per_day = max(1, int(round(1440 / max(1, int(
            getattr(ctx, "eval_freq_minutes", 1440) or 1440)))))
        if bars_per_day > 1:
            n_days = len(vols_raw) // bars_per_day
            vols = np.array([vols_raw[i * bars_per_day:(i + 1) * bars_per_day].sum()
                             for i in range(n_days)]) if n_days else np.array([])
        else:
            vols = vols_raw

        if len(vols) == 0 or vols[0] <= 0:
            return out
        day1_vol = float(vols[0])

        # Day numbering: Day 1 close = iloc[0], Day N close = iloc[N-1].
        # We need len(vols) >= check_day to have observed the Day-N close.
        if len(vols) >= self.check_day:
            if self.check_day == 14:
                # R-2-aligned: mean(vol[7:14]) / vol[0] — positions 7..13
                # = Days 8..14, all observable at Day 14 close.
                window = vols[7:14]
            elif self.check_day == 7:
                # Partial: mean(vol[1:7]) / vol[0] — positions 1..6 = Days 2..7.
                window = vols[1:7]
            else:
                # Generic fallback: positions 1..(check_day-1) inclusive.
                end_pos = min(self.check_day, len(vols))
                window = vols[1:end_pos]
            if len(window) >= 1 and day1_vol > 0:
                vc = float(window.mean()) / day1_vol
                if vc >= self.vol_cliff_hi_threshold:
                    # Set +1.0 from position (check_day - 1) onward — that's
                    # the Day-N close bar itself plus every later bar (so a
                    # missed cron tick on Day N still trips the exit on the
                    # next cycle).
                    sig_col = out.columns.get_loc("bnldex_signal")
                    # ⚠ 위치도 **봉 단위**로 환산한다 — 일 인덱스를 그대로
                    #   쓰면 1h 에서 Day 7 이 7번째 시간봉이 된다.
                    first_bar = (self.check_day - 1) * bars_per_day
                    out.iloc[first_bar:, sig_col] = 1.0
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
            _c = "bnldex_signal"
            out.loc[(out.index > _entry_end) & (out[_c] < 0), _c] = 0.0
            out.loc[out.index > _all_end, _c] = 0.0
        return out
