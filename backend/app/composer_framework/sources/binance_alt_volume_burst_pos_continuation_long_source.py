"""BinanceAltVolumeBurstPosContinuationLongSource — paradigm 127 R-4 PASS live signal.

Hypothesis (R-4 PASS 2026-05-21, paradigm 127 — paradigm 126 A-arm split)
-----------------------------------------------------------------------
Per alt 1m bar:
  trigger_bar :=  vol_1m  >  trailing 30d rolling p99 of 1m volume
              AND |ret_1m| > 0.005 (0.5%)
              AND ret_1m > 0   (positive burst)

Aggregation (MANDATORY Lesson #50 guardrail):
  Within each 5-minute bin (e.g. 12:00:00..12:04:59) emit AT MOST ONE event
  whose sign is taken from the FIRST 1m bar in the bin that satisfies
  the trigger. Subsequent 1m bursts within the same 5m bin are IGNORED
  (per-burst signing is a Lesson #50 antipattern: sigex dilution 0.66×,
  +38% event inflation with overlapping forward windows).

Per-symbol debounce (MANDATORY R-3 caveat 3):
  After a fire, suppress new triggers for the next 30 minutes on the
  same symbol. Retains 74.06% of events with 13/13 sym ci_pos preserved.

Action -> LONG hold = 75 minutes (R-3 caveat 1 sweet-spot;
                                  hold60→75 +6.1% edge,
                                  hold75→90 +0.3% marginal plateau)
TP / SL: none in measurement (raw fwd_ret hold-to-completion).
         A live trader may overlay a -5% SL / +10% TP for risk control,
         but R-3 metrics assume hold-to-completion at max_hold_bars.

R-1 ~ R-4 evidence (2026-05-21)
-------------------------------
R-1 focus pos LONG:
  n=13,176 / gross +70.94bp / net +54.94bp / sigex +49.83
  ci [+45.90, +63.96] / perm_p 0.000 / 13/13 syms ci_pos
R-2 walk-forward:
  TS-CV 5/5 PASS, broad-shoulders top-3 exclusion 85% retention,
  slippage 20bp ann_gross 3,066%, util 34.3%
R-3 primary baseline (hold60):
  n=13,175 / gross +78.65bp / net +62.65bp / sigex +43.96
  ci [+50.11, +74.93] / trades/yr 6,019 / ann_gross 4,734%
R-3 caveat 1 sweet-spot (hold75):
  ann_gross 5,021% / net +67.43bp / per-trade edge 0.674%
R-3 caveats 6/7 PASS (per-burst FAIL Lesson #50 OVERRIDE)
R-3 OOS 2026Q1+Q2:
  n=1,979 / sigex +19.42 (paradigm 117 graveyard precedent 10× safety)
  ci_lower +30.91bp / 10/13 syms ci_pos
R-4 verdict: PASS_R4_HIGH_FREQ_DIFFUSE_SMALL_CAPITAL (7/7 gates,
                                                      Capacity Class C $10k)

Architecture
------------
This source runs on each ALT's per-symbol paper session. Source state is
purely a function of that symbol's 1m OHLCV (no leader injection needed).

For each ALT session:
  1. Resample ctx.ohlcv_eval (assumed 5m frequency) to 1m via ctx.ohlcv_1m.
  2. For each 1m bar compute:
       vol_1m, ret_1m, p99_30d trailing
  3. Identify trigger bars (vol_1m > p99 AND |ret_1m|>0.005 AND ret_1m>0).
  4. Apply 5m-bin first-burst-sign aggregation (Lesson #50).
  5. Apply per-sym 30-min debounce.
  6. Map retained trigger 1m timestamps -> eval (5m) bar timestamps
     (asof backward — eval bar that contains the trigger).
  7. Emit +1.0 LONG signal on those bars; 0.0 elsewhere.

Pair with:
  composer: passthrough(feature_col=bnvbpl_signal, scale=1.0)
  policy:   long_short_threshold(entry_threshold=0.5, sl_pct=0.99 (none),
                                 tp_pct=0.99 (none), max_hold_bars=15
                                 i.e. 75min at 5m eval granularity)
  config:   eval_freq_minutes=5, forward_bars=15

Output (single signal column + debug, prefix `bnvbpl_`):
  bnvbpl_signal — {0.0, +1.0} discrete (LONG only)
  bnvbpl_burst_z — burst-bar |ret_1m| × 100 (debug, % magnitude)
  bnvbpl_vol_pct — burst-bar vol rank within trailing 30d window (debug)
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext

log = logging.getLogger("bn_alt_volume_burst_pos_continuation_long")


class BinanceAltVolumeBurstPosContinuationLongSource(SignalSource):
    """paradigm 127 — 1m volume burst positive continuation LONG, 75min hold."""

    name = "bn_alt_volume_burst_pos_continuation_long"
    feature_prefix = "bnvbpl_"
    requires = ("ohlcv_eval",)

    # Paradigm config (frozen at R-4 PASS, 2026-05-21)
    VOL_LOOKBACK_DAYS = 30
    VOL_LOOKBACK_BARS_1M = 30 * 24 * 60  # 43,200 1m bars
    VOL_PERCENTILE = 99.0
    MAGNITUDE_THRESHOLD = 0.005   # |1m_ret| > 0.5%
    BURST_SIGN_FILTER = "positive"  # ret_1m > 0
    AGGREGATION_BIN_MIN = 5        # first-burst-sign per 5m bin
    DEBOUNCE_MIN = 30              # per-symbol cool-off after fire

    def __init__(
        self,
        *,
        volume_percentile: float = 99.0,
        magnitude_threshold: float = 0.005,
        aggregation_bin_min: int = 5,
        debounce_min: int = 30,
    ) -> None:
        self.volume_percentile = float(volume_percentile)
        self.magnitude_threshold = float(magnitude_threshold)
        self.aggregation_bin_min = int(aggregation_bin_min)
        self.debounce_min = int(debounce_min)

    # ─────────────────────────────────────────────────── helpers ───

    @staticmethod
    def _to_1m(ctx: SourceContext) -> Optional[pd.DataFrame]:
        """Return 1m OHLCV. Prefer ctx.ohlcv_1m; fall back to ohlcv_eval if 1m."""
        if ctx.ohlcv_1m is not None and len(ctx.ohlcv_1m) > 0:
            return ctx.ohlcv_1m
        if ctx.eval_freq_minutes == 1 and ctx.ohlcv_eval is not None:
            return ctx.ohlcv_eval
        return None

    def _compute_triggers(self, ohlcv_1m: pd.DataFrame) -> pd.DataFrame:
        """Return DataFrame indexed by retained 1m trigger timestamp with cols
        sign (+1 only here), burst_z (=|ret_1m|*100), vol_pct.

        Apply (in order):
          1. base trigger: vol>p99 AND |ret|>0.5% AND ret>0
          2. 5m-bin first-burst-sign aggregation (Lesson #50 guardrail)
          3. per-sym 30min debounce
        """
        if ohlcv_1m is None or len(ohlcv_1m) == 0:
            return pd.DataFrame()
        if not {"close", "volume"}.issubset(ohlcv_1m.columns):
            return pd.DataFrame()

        df = ohlcv_1m.copy()
        df.index = pd.to_datetime(df.index)

        # 1m return
        df["ret_1m"] = df["close"].pct_change()

        # 30d rolling p99 of 1m volume
        # Use min_periods = a fraction of the window so trigger fires after
        # ~7d of history rather than waiting full 30d (live cold-start safe).
        min_periods = max(int(self.VOL_LOOKBACK_BARS_1M * 0.25), 1)
        df["vol_p99"] = (
            df["volume"]
            .rolling(self.VOL_LOOKBACK_BARS_1M, min_periods=min_periods)
            .quantile(self.volume_percentile / 100.0)
        )
        # vol percentile rank for debug (within trailing window)
        df["vol_pct"] = (
            df["volume"]
            .rolling(self.VOL_LOOKBACK_BARS_1M, min_periods=min_periods)
            .rank(pct=True)
        )

        # base trigger
        fire = (
            (df["volume"] > df["vol_p99"])
            & (df["ret_1m"].abs() > self.magnitude_threshold)
            & (df["ret_1m"] > 0.0)
        ) & df["vol_p99"].notna()

        triggers = df[fire].copy()
        if len(triggers) == 0:
            return pd.DataFrame()

        triggers["sign"] = 1.0
        triggers["burst_z"] = triggers["ret_1m"].abs() * 100.0

        # ─── (2) 5m bin first-burst-sign aggregation ───
        # Truncate each 1m timestamp to its containing 5m bin start.
        bin_start = triggers.index.floor(f"{self.aggregation_bin_min}min")
        triggers["_bin"] = bin_start
        # Keep only the FIRST trigger per bin (idx is monotonic so sorting OK).
        triggers = triggers.sort_index()
        first_in_bin = triggers.groupby("_bin", as_index=False).head(1).copy()
        first_in_bin = first_in_bin.drop(columns=["_bin"])

        # ─── (3) per-sym 30min debounce ───
        if len(first_in_bin) == 0:
            return first_in_bin
        keep_mask = [True]
        last_t = first_in_bin.index[0]
        for ts in first_in_bin.index[1:]:
            delta_min = (ts - last_t).total_seconds() / 60.0
            if delta_min < self.debounce_min:
                keep_mask.append(False)
            else:
                keep_mask.append(True)
                last_t = ts
        retained = first_in_bin[keep_mask]

        return retained[["sign", "burst_z", "vol_pct"]]

    # ─────────────────────────────────────────────────── interface ───

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        eval_idx = pd.to_datetime(ctx.ohlcv_eval.index)
        out = pd.DataFrame(index=eval_idx)
        out["bnvbpl_signal"] = 0.0
        out["bnvbpl_burst_z"] = np.nan
        out["bnvbpl_vol_pct"] = np.nan

        ohlcv_1m = self._to_1m(ctx)
        if ohlcv_1m is None or len(ohlcv_1m) == 0:
            log.warning(
                "bn_alt_volume_burst_pos_continuation_long: 1m ohlcv missing "
                "(ctx.ohlcv_1m empty and eval_freq != 1m) — emitting zero signal"
            )
            return out

        triggers = self._compute_triggers(ohlcv_1m)
        if len(triggers) == 0:
            return out

        # Map 1m trigger timestamps -> eval bar (asof backward).
        eval_sorted = pd.DatetimeIndex(eval_idx).sort_values()
        for ts, row in triggers.iterrows():
            pos = eval_sorted.searchsorted(ts, side="right") - 1
            if pos < 0 or pos >= len(eval_sorted):
                continue
            bar_ts = eval_sorted[pos]
            out.loc[bar_ts, "bnvbpl_signal"] = float(row["sign"])
            out.loc[bar_ts, "bnvbpl_burst_z"] = float(row["burst_z"])
            out.loc[bar_ts, "bnvbpl_vol_pct"] = float(row["vol_pct"])

        return out
