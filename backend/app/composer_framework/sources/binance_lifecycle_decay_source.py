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
"""
from __future__ import annotations

import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext


class BinanceLifecycleDecaySource(SignalSource):
    name = "bn_lifecycle_decay"
    feature_prefix = "bnld_"
    requires = ("ohlcv_eval",)

    def __init__(self) -> None:
        pass

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        idx = pd.to_datetime(ctx.ohlcv_eval.index)
        out = pd.DataFrame(index=idx)
        # Constant short signal. Once policy enters at first cycle, subsequent
        # cycles' signal value is ignored (policy.in_position branch).
        out["bnld_signal"] = -1.0
        return out
