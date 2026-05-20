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
    ) -> None:
        self.btc_30d_pre_ret = float(btc_30d_pre_ret)
        self.bear_threshold = float(bear_threshold)

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        idx = pd.to_datetime(ctx.ohlcv_eval.index)
        out = pd.DataFrame(index=idx)
        is_bear = self.btc_30d_pre_ret <= self.bear_threshold
        out["bnldbs_signal"] = 0.0 if is_bear else -1.0
        return out
