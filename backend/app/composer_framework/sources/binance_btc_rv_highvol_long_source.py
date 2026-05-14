"""BinanceBTCRVHighvolLongSource — paradigm 69 (R-4 PASS 2026-05-14) live signal.

Hypothesis
----------
BTC 30-min realized volatility z-score(30d rolling) >= +2.5 (rising edge
+ 60-min cooldown) AND BTC 30-min return > 0 at trigger AND BTC current 30d
rolling vol >= p90 of past 90d distribution (HIGH vol regime) all hold
  -> LONG 13 alts (ADA, AVAX, BCH, BNB, DOGE, ETH, FIL, LINK, LTC, NEAR,
     SOL, WIF, XRP), hold 240 min, TP +5%, no SL.

Mechanism: high-vol regime + additional RV z-spike + price-up = vol cascade
momentum (leverage stress → liquidation cascade up-side → 4h tail).

R-1 ~ R-4 evidence (2026-05-14, Mint 380-day OHLCV):
  n_trades = 455 (35 HIGH-vol up-triggers x 13 alts)
  net_mean = +126.28 bp (fee-adjusted), t = +11.11, win = 52.9%
  signal_t_excess = +12.26 (null_mean_t = -1.13)
  bootstrap CI [+116.11, +128.29] bp, prob_positive = 1.0
  perm_p_one_sided_above = 0.000
  plateau 96/96 cells (strict 4-gate)
  per-sym 13/13 net positive
  R-3 inter-paradigm cosine vs 68th parent = 0.42 (distinct sub-paradigm)
  WF 5-fold: 4/5 positive (Fold 4 n=0 from dry Jan-2026 period)
  Within-HIGH stratification: 0 killer subregime
  Funding-cost-adjusted (66% trades span 1bp/8h): net +125.62 bp t=+11.05

Architecture
------------
This source runs on each ALT's per-symbol paper session. BTC OHLCV is
injected via `runtime_bundle.leader_ohlcv_1m` (added by paper_session_cli
when 'bn_btc_rv_highvol_long' is in sources_used).

For each ALT session:
  1. Read BTC 1m raw from leader_ohlcv_1m.
  2. Compute BTC RV 30m, z-score over 30d (43200 1m bars), trigger
     rising-edge >= +2.5 with 60-min cooldown.
  3. Filter: BTC 30m return > 0 AND BTC 30d rolling vol >= p90 of past 90d.
  4. Map trigger timestamps to alt's eval index (asof forward fill within
     same eval bar).
  5. Emit +1.0 LONG signal at trigger eval bar, 0.0 elsewhere.

Pair with:
  composer: passthrough (feature_col=bnrvh_signal, scale=1.0)
  policy:   long_short_threshold (entry_threshold=0.5, sl_pct=0.99
            i.e. effectively none, tp_pct=0.05, max_hold_bars=54
            i.e. 270 min at 5m eval granularity)
  config:   eval_freq_minutes=5, forward_bars=54

Output (single signal column, prefix `bnrvh_`):
  bnrvh_signal — {0.0, +1.0} discrete (LONG only)
  bnrvh_rv_z   — BTC RV z-score at corresponding bar (debug)
  bnrvh_vol_p  — BTC 30d vol percentile in 90d distribution (debug)
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext

log = logging.getLogger("bn_btc_rv_highvol_long")


class BinanceBTCRVHighvolLongSource(SignalSource):
    name = "bn_btc_rv_highvol_long"
    feature_prefix = "bnrvh_"
    requires = ("ohlcv_eval",)  # leader_ohlcv_1m injected by paper_session_cli

    # Paradigm config (frozen at R-4 PASS, 2026-05-14)
    RV_WINDOW_MIN = 30          # BTC 30-min realized vol window
    Z_WINDOW_BARS = 30 * 24 * 60  # 30d rolling z-score (43200 1m bars)
    Z_THRESH = 2.5              # |z| >= 2.5 rising edge
    COOLDOWN_MIN = 60           # 60-min cooldown between triggers
    VOL_LOOKBACK_BARS = 30 * 24 * 60  # current 30d vol
    VOL_DIST_BARS = 90 * 24 * 60      # 90d distribution
    VOL_PCT_CUTOFF = 0.90       # p90 of past 90d (HIGH vol regime)

    def __init__(
        self,
        leader_ohlcv_1m: Optional[pd.DataFrame] = None,
        z_thresh: float = 2.5,
        vol_pct_cutoff: float = 0.90,
    ) -> None:
        # leader_ohlcv_1m can be injected via constructor (offline backtest)
        # or via runtime_bundle.leader_ohlcv_1m (live paper session).
        self._init_leader = leader_ohlcv_1m
        self.z_thresh = float(z_thresh)
        self.vol_pct_cutoff = float(vol_pct_cutoff)

    def _get_leader(self, ctx: SourceContext) -> Optional[pd.DataFrame]:
        if self._init_leader is not None and len(self._init_leader) > 0:
            return self._init_leader
        return getattr(ctx, "leader_ohlcv_1m", None)

    def _compute_btc_triggers(self, btc_1m: pd.DataFrame) -> pd.DataFrame:
        """Return DataFrame indexed by trigger timestamp (1m bar) with columns
        rv_z, btc_ret_30m, vol_pct.
        """
        if btc_1m is None or len(btc_1m) == 0 or "close" not in btc_1m.columns:
            return pd.DataFrame()

        lr = np.log(btc_1m["close"]).diff()

        # 30-min RV
        rv = lr.rolling(self.RV_WINDOW_MIN, min_periods=self.RV_WINDOW_MIN).std()

        # 30d z-score of RV
        rv_mu = rv.rolling(self.Z_WINDOW_BARS, min_periods=self.Z_WINDOW_BARS).mean()
        rv_sd = rv.rolling(self.Z_WINDOW_BARS, min_periods=self.Z_WINDOW_BARS).std()
        rv_z = (rv - rv_mu) / rv_sd

        # BTC 30m return
        btc_ret_30m = btc_1m["close"] / btc_1m["close"].shift(self.RV_WINDOW_MIN) - 1

        # 30d rolling vol (for regime classification)
        vol_30d = lr.rolling(self.VOL_LOOKBACK_BARS, min_periods=self.VOL_LOOKBACK_BARS).std()

        # 90d distribution percentile (rolling)
        # Compute percentile rank of vol_30d within past 90d window
        vol_pct = vol_30d.rolling(self.VOL_DIST_BARS, min_periods=self.VOL_DIST_BARS).rank(pct=True)

        sig = pd.DataFrame({
            "rv": rv,
            "rv_z": rv_z,
            "btc_ret_30m": btc_ret_30m,
            "vol_pct": vol_pct,
        }).dropna()

        if len(sig) == 0:
            return sig

        # Rising-edge trigger
        z_prev = sig["rv_z"].shift(1)
        fire = (sig["rv_z"] > self.z_thresh) & (z_prev <= self.z_thresh)
        triggers = sig[fire].copy()

        # Filter: BTC up + HIGH vol regime
        triggers = triggers[triggers["btc_ret_30m"] > 0]
        triggers = triggers[triggers["vol_pct"] >= self.vol_pct_cutoff]

        if len(triggers) == 0:
            return triggers

        # 60-min cooldown
        keep = [True]
        last_t = triggers.index[0]
        for ts in triggers.index[1:]:
            delta_min = (ts - last_t).total_seconds() / 60.0
            if delta_min < self.COOLDOWN_MIN:
                keep.append(False)
            else:
                keep.append(True)
                last_t = ts
        return triggers[keep]

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        eval_idx = pd.to_datetime(ctx.ohlcv_eval.index)
        out = pd.DataFrame(index=eval_idx)
        out["bnrvh_signal"] = 0.0
        out["bnrvh_rv_z"] = np.nan
        out["bnrvh_vol_p"] = np.nan

        leader = self._get_leader(ctx)
        if leader is None or len(leader) == 0:
            log.warning("bn_btc_rv_highvol_long: leader BTC ohlcv missing — emitting zero signal")
            return out

        triggers = self._compute_btc_triggers(leader)
        if len(triggers) == 0:
            return out

        # Map BTC 1m trigger timestamps -> alt's eval index.
        # eval_idx may be 1m / 5m / 15m. For each trigger ts, find the eval
        # bar whose timestamp is the largest one <= ts (asof backward).
        eval_sorted = pd.DatetimeIndex(eval_idx).sort_values()
        for ts, row in triggers.iterrows():
            # Find the eval bar that contains this trigger
            pos = eval_sorted.searchsorted(ts, side="right") - 1
            if pos < 0 or pos >= len(eval_sorted):
                continue
            bar_ts = eval_sorted[pos]
            out.loc[bar_ts, "bnrvh_signal"] = 1.0
            out.loc[bar_ts, "bnrvh_rv_z"] = row["rv_z"]
            out.loc[bar_ts, "bnrvh_vol_p"] = row["vol_pct"]

        return out
