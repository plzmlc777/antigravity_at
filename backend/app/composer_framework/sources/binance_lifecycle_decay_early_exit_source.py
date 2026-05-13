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
"""
from __future__ import annotations

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
    ) -> None:
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

        vols = df["volume"].astype(float).values
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
                    out.iloc[self.check_day - 1:, sig_col] = 1.0
        return out
