"""BinancePremiumVelocityZScoreSource — daily premium velocity z-score signal.

Hypothesis (Research Track paradigm `premium_velocity_zscore`, R-3 PASS
2026-05-06, queue 첫 break-through):

  Daily premium velocity = premium_close[t] - premium_close[t-1] (1st
  derivative). 30-day rolling z-score of velocity. When |vel_z| > entry_z
  (default 1.0), follow direction:
  - vel_z > +entry_z → LONG (premium accelerating up = momentum)
  - vel_z < -entry_z → SHORT (premium accelerating down)
  - hold for hold_days, exit on SL.

R-3 stats (n=200 perm, follow ez=1.0 h=5):
  AVAXUSDT: alpha 365.86 sharpe 2.42 PF 2.25 mdd 46.6 wr 64.0 perm_p 0.000 6.86σ
  HBARUSDT: perm_p 0.000 5.25σ (R-2 alpha pos, full strict TBD)
  SOLUSDT:  alpha 184.40 sharpe 1.87 PF 2.08 mdd 35.2 wr 63.0 perm_p 0.000 4.88σ
  UNIUSDT:  alpha 287.40 sharpe 1.81 perm_p 0.015 3.54σ borderline

Distinct from existing bn_premium_index_zscore (level z-score paradigm):
  - Level (0차): when premium IS extreme. velocity (1차): when premium IS
    accelerating. Different timing — velocity fires earlier in the trend.
  - Different symbols seed under each: AVAX/HBAR strong on velocity
    (not seeded on level), SOL strong on both (level was seeded).

Output (prefix `bnpvz_`):
  bnpvz_signal — discrete in {-1.0, 0.0, +1.0}
  bnpvz_z      — rolling 30-day z-score of premium velocity (debug)

Combine with `PassthroughComposer` + `LongShortThresholdPolicy` (entry 0.5,
sl_pct=0.05, max_hold_bars=5, eval_freq_minutes=1440 daily).

Runtime data: `runtime['premium_df']` (joblib daily premium with `close`).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext


class BinancePremiumVelocityZScoreSource(SignalSource):
    name = "bn_premium_velocity_zscore"
    feature_prefix = "bnpvz_"
    requires = ("ohlcv_eval",)

    def __init__(self,
                 premium_df: pd.DataFrame | None = None,
                 zwin: int = 30,
                 entry_z: float = 1.0) -> None:
        self.premium_df = premium_df
        self.zwin = int(zwin)
        self.entry_z = float(entry_z)

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        eval_idx = pd.to_datetime(ctx.ohlcv_eval.index)
        out = pd.DataFrame(index=eval_idx)

        if (self.premium_df is None or len(self.premium_df) == 0
                or "close" not in self.premium_df.columns):
            out["bnpvz_signal"] = 0.0
            out["bnpvz_z"] = np.nan
            return out

        df = self.premium_df[["close"]].copy()
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df = df.dropna(subset=["close"])
        df.index = pd.to_datetime(df.index).normalize()
        df = df.sort_index()
        df = df[~df.index.duplicated(keep="last")]

        if len(df) < self.zwin + 5:
            out["bnpvz_signal"] = 0.0
            out["bnpvz_z"] = np.nan
            return out

        velocity = df["close"].diff()
        rmean = velocity.rolling(self.zwin).mean()
        rstd = velocity.rolling(self.zwin).std()
        vel_z = (velocity - rmean) / rstd.replace(0, np.nan)

        signal = pd.Series(0.0, index=df.index)
        signal[vel_z > self.entry_z] = 1.0    # follow LONG (accelerating up)
        signal[vel_z < -self.entry_z] = -1.0  # follow SHORT (accelerating down)

        eval_norm = eval_idx.normalize()
        union_idx = pd.DatetimeIndex(sorted(set(signal.index) | set(eval_norm)))
        sig_ff = signal.reindex(union_idx).ffill().fillna(0.0).reindex(eval_norm)
        z_ff = vel_z.reindex(union_idx).ffill().reindex(eval_norm)

        out["bnpvz_signal"] = sig_ff.astype(float).values
        out["bnpvz_z"] = z_ff.astype(float).values
        return out
