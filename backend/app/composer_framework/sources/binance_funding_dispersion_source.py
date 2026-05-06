"""BinanceFundingDispersionSource — cross-section funding-rate z-score signal.

Hypothesis (Research Track paradigm `funding_dispersion`, R-3 PASS perm_p=0.000
on ETCUSDT): at each 8h funding boundary, the cross-section distribution of
funding rates across the universe reveals which symbols are over/under-crowded
relative to peers. A symbol whose funding rate sits many σ above the universe
mean is reversal-prone (excess long pressure → SHORT entry); below the mean
implies oversold shorts paying funding → LONG entry.

Distinct from `BinanceFundingZScoreSource` (paradigm `funding_carry`):
  - funding_carry: per-symbol time-series z (own rolling history)
  - funding_dispersion: cross-section z (peer-relative position at same instant)
  Both can fire independently — e.g. all symbols high funding (carry-z high,
  dispersion-z low for each individual symbol).

Output (one signal column, prefix `bnfd_`):
  bnfd_signal — discrete in {-1.0, 0.0, +1.0}:
    +1 → enter LONG  (xs_z < -entry_z, undercrowded)
    -1 → enter SHORT (xs_z > +entry_z, overcrowded)
     0 → no signal
  bnfd_xs_z   — raw cross-section z-score (debug / ML fallback)
  bnfd_funding_rate — own funding rate (debug)

Combine with `PassthroughComposer` (no negation) + `LongShortThresholdPolicy`
(entry_threshold=0.5) — same wiring as autocorr_regime.

Universe data ingest: pass `funding_universe_df` — a pandas DataFrame of
shape (n_periods, n_symbols) with funding_time index and symbol columns. The
source extracts the target symbol's column for the own funding_rate series and
computes xs_z = (own − xs_mean) / xs_std at each timestamp.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext


class BinanceFundingDispersionSource(SignalSource):
    name = "bn_funding_dispersion"
    feature_prefix = "bnfd_"
    requires = ("ohlcv_eval",)

    def __init__(self,
                 funding_universe_df: pd.DataFrame | None = None,
                 target_symbol: str = "",
                 entry_z: float = 0.8) -> None:
        """
        Args:
          funding_universe_df: wide df with columns=symbols, index=funding_time,
            values=funding_rate. Must include `target_symbol`.
          target_symbol: which symbol's column to emit signal for.
          entry_z: |xs_z| threshold for signal emission (matches PoC ez param).
        """
        self.funding_universe_df = funding_universe_df
        self.target_symbol = str(target_symbol)
        self.entry_z = float(entry_z)

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        eval_idx = pd.to_datetime(ctx.ohlcv_eval.index)
        out = pd.DataFrame(index=eval_idx)

        if (self.funding_universe_df is None
                or len(self.funding_universe_df) == 0
                or self.target_symbol not in self.funding_universe_df.columns):
            out["bnfd_signal"] = 0.0
            out["bnfd_xs_z"] = np.nan
            out["bnfd_funding_rate"] = np.nan
            return out

        f = self.funding_universe_df.copy()
        # Ensure index is DatetimeIndex
        f.index = pd.to_datetime(f.index)
        f = f.sort_index()

        # Cross-section mean/std at each funding boundary across columns
        xs_mean = f.mean(axis=1)
        xs_std = f.std(axis=1, ddof=1).replace(0, np.nan)

        own = f[self.target_symbol]
        xs_z = (own - xs_mean) / xs_std

        # Discrete signal at each funding period
        signal = pd.Series(0.0, index=xs_z.index)
        signal[xs_z > self.entry_z] = -1.0   # SHORT (overcrowded long)
        signal[xs_z < -self.entry_z] = 1.0   # LONG  (oversold short)

        # Forward-fill from funding-time grid onto eval index
        # Build a series union, ffill, then reindex to eval_idx.
        union_idx = pd.DatetimeIndex(sorted(set(signal.index) | set(eval_idx)))
        sig_ff = signal.reindex(union_idx).ffill().fillna(0.0).reindex(eval_idx)
        z_ff = xs_z.reindex(union_idx).ffill().reindex(eval_idx)
        own_ff = own.reindex(union_idx).ffill().reindex(eval_idx)

        out["bnfd_signal"] = sig_ff.astype(float).values
        out["bnfd_xs_z"] = z_ff.astype(float).values
        out["bnfd_funding_rate"] = own_ff.astype(float).values
        return out
