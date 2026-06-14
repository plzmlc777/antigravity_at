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

from app.composer_framework.signal_source import (
    InsufficientSourceDataError,
    SignalSource,
    SourceContext,
)

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

    # vol_pct needs VOL_LOOKBACK_BARS warmup for vol_30d, then VOL_DIST_BARS
    # more to rank it within the 90d window → ~120d of BTC 1m before the FIRST
    # bar can ever fire. Demand at least this much usable eval window beyond
    # that warmup, else the signal is structurally suppressed (the failure that
    # left 13 btc_rv sessions silently at 0 trades on a 139d BTC leader).
    MIN_EVAL_WINDOW_BARS = 30 * 24 * 60   # ≥30d usable window after warmup
    # 1m leader may lag the eval window by at most this before it's "stale".
    STALE_TOLERANCE_MIN = 2 * 24 * 60     # 2 days

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
            raise InsufficientSourceDataError(
                f"{self.name}[{ctx.symbol}]: leader BTC 1m ohlcv missing "
                f"(leader_ohlcv_1m not injected). Refusing to emit a fake zero "
                f"signal."
            )

        # History-sufficiency guard: vol_pct needs warmup + a usable window.
        # Below this, the vol-regime filter is NaN over (almost) the whole eval
        # span and the source can only ever emit zeros — indistinguishable from
        # a real "no high-vol cascade" period unless we fail loudly here.
        min_leader_bars = (
            self.VOL_LOOKBACK_BARS + self.VOL_DIST_BARS + self.MIN_EVAL_WINDOW_BARS
        )
        if len(leader) < min_leader_bars:
            raise InsufficientSourceDataError(
                f"{self.name}[{ctx.symbol}]: BTC 1m leader too short — have "
                f"{len(leader)} bars (~{len(leader) // 1440}d), need "
                f"≥{min_leader_bars} (~{min_leader_bars // 1440}d) for "
                f"{(self.VOL_LOOKBACK_BARS + self.VOL_DIST_BARS) // 1440}d vol "
                f"warmup + {self.MIN_EVAL_WINDOW_BARS // 1440}d usable window. "
                f"Backfill BTCUSDT 1m before trusting this session."
            )

        # Staleness guard: leader must overlap the eval window, else recent
        # triggers can't be mapped and the signal silently flatlines.
        eval_end = eval_idx.max()
        leader_end = pd.to_datetime(leader.index).max()
        lag_min = (eval_end - leader_end).total_seconds() / 60.0
        if lag_min > self.STALE_TOLERANCE_MIN:
            raise InsufficientSourceDataError(
                f"{self.name}[{ctx.symbol}]: BTC 1m leader stale — last bar "
                f"{leader_end} lags eval end {eval_end} by {lag_min / 1440:.1f}d "
                f"(> {self.STALE_TOLERANCE_MIN / 1440:.0f}d tolerance)."
            )

        # Data is sufficient: an empty trigger set here is a LEGITIMATE
        # "no high-vol up-cascade fired" period → valid all-zero signal.
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
