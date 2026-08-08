"""BinanceAltVolumeBurstNegReversionShortSource — paradigm 128 R-4 PASS live signal.

Hypothesis (R-4 PASS 2026-05-21, paradigm 128 — paradigm 126 B-arm split)
-----------------------------------------------------------------------
Per alt 1m bar:
  trigger_bar :=  vol_1m  >  trailing 30d rolling p99 of 1m volume
              AND |ret_1m| > 0.005 (0.5%)
              AND ret_1m < 0    (negative / capitulation burst)

Aggregation (MANDATORY Lesson #50 guardrail):
  Within each 5-minute bin emit AT MOST ONE event whose sign is taken
  from the FIRST 1m bar in the bin that satisfies the trigger. Subsequent
  negative bursts within the same 5m bin are IGNORED (per-burst signing
  is a Lesson #50 antipattern; for paradigm 128 specifically it INVERTS
  the alpha — net -34.61bp ci_lower -49.17 — because cascading negative
  bursts within 5m represent already-priced sell-off / information
  saturated; first-burst captures the lead-edge capitulation only).

Per-symbol debounce (MANDATORY R-3 caveat 3):
  After a fire, suppress new triggers for the next 30 minutes on the
  same symbol.

Action -> SHORT hold = 10 minutes (R-3 caveat 1 sweet-spot vs 15min
                                   originally specified; +9.2% edge
                                   uplift, +14% sharpe uplift)

MANDATORY risk controls (R-4 Gate 4):
  SL = 0.5% per trade (caps single-trade loss; max-adverse pre-SL was
                       129.88% in the worst observed squeeze. SL=0.5%
                       truncates left tail; stress test ann_gross 1,990%
                       post-SL / 1,786% post-SL+10bp slip)
  TP = none (10min hold exits before TP would meaningfully trigger).

OPERATIONAL CAVEAT (encoded in seed_spec, not in policy):
  Skip entry if per-symbol 8h funding rate > +3bp at trigger time.
  Reason: SHORT pays funding when funding rate positive; at +3bp/8h the
  expected funding drag exceeds the per-trade edge margin. The current
  LongShortThresholdPolicy lacks a funding-aware hook; this must be
  enforced by a wrapper policy or operational monitor at deploy time.
  Flagged as Day 7 monitoring requirement.

R-1 ~ R-4 evidence (2026-05-21)
-------------------------------
R-3 primary baseline:
  n=14,843 (2.2yr) / sigex +63.67 / 13/13 syms ci_pos
R-3 caveat 1 hold=10min sweet-spot:
  gross +55.80bp / net +39.80bp / per-trade edge 0.398%
R-3 OOS 2026Q1+Q2:
  sigex +28.89 / ci_lower +34.80 / 1.48× IS edge ratio
  (paradigm 117 0.65× fragility avoided)
R-3 caveats 6/7 PASS (per-burst FAIL Lesson #50 OVERRIDE; both A+B arms
  exhibit identical antipattern — paradigm 127 dilution / paradigm 128
  inversion — dual-dogfood Lesson #50 CONFIRMED 자격)
R-4 verdict: PASS_R4_DUAL_MODE_HIGH_FREQ_DIFFUSE_SHORT_WITH_MANDATORY_SL
  (8/8 gates; ann_gross post-SL 1,990% / sharpe pre-SL 12.23 /
   estimated stop_rate 25.7%)

Architecture
------------
Identical to paradigm 127 source pattern. Per-symbol paper session,
self-contained on that symbol's 1m OHLCV. Source emits -1.0 on retained
negative-burst trigger bars; LongShortThresholdPolicy maps pred < -0.5
to enter_short with sl_price = open × 1.005.

Pair with:
  composer: passthrough(feature_col=bnvbns_signal, scale=1.0)
  policy:   long_short_threshold(entry_threshold=0.5, sl_pct=0.005
                                 MANDATORY, tp_pct=0.99 (none),
                                 max_hold_bars=2 i.e. 10min at 5m
                                 eval granularity)
  config:   eval_freq_minutes=5, forward_bars=2

Output (single signal column + debug, prefix `bnvbns_`):
  bnvbns_signal — {0.0, -1.0} discrete (SHORT only)
  bnvbns_burst_z — burst-bar |ret_1m| × 100 (debug, % magnitude)
  bnvbns_vol_pct — burst-bar vol rank within trailing 30d window (debug)
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext

log = logging.getLogger("bn_alt_volume_burst_neg_reversion_short")


class BinanceAltVolumeBurstNegReversionShortSource(SignalSource):
    """paradigm 128 — 1m volume burst negative capitulation reversion SHORT,
    10min hold, SL=0.5% MANDATORY."""

    name = "bn_alt_volume_burst_neg_reversion_short"
    feature_prefix = "bnvbns_"
    requires = ("ohlcv_eval",)

    # Paradigm config (frozen at R-4 PASS, 2026-05-21)
    VOL_LOOKBACK_DAYS = 30
    VOL_LOOKBACK_BARS_1M = 30 * 24 * 60  # 43,200 1m bars
    VOL_PERCENTILE = 99.0
    MAGNITUDE_THRESHOLD = 0.005   # |1m_ret| > 0.5%
    BURST_SIGN_FILTER = "negative"  # ret_1m < 0
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
        if ctx.ohlcv_1m is not None and len(ctx.ohlcv_1m) > 0:
            return ctx.ohlcv_1m
        if ctx.eval_freq_minutes == 1 and ctx.ohlcv_eval is not None:
            return ctx.ohlcv_eval
        return None

    def _compute_triggers(self, ohlcv_1m: pd.DataFrame) -> pd.DataFrame:
        """Return DataFrame indexed by retained 1m trigger timestamp with cols
        sign (-1 only here), burst_z, vol_pct.

        Apply (in order):
          1. base trigger: vol>p99 AND |ret|>0.5% AND ret<0
          2. 5m-bin first-burst-sign aggregation (Lesson #50 — for SHORT
             arm this guardrail is even more critical since per-burst INVERTS
             the alpha rather than merely diluting it)
          3. per-sym 30min debounce
        """
        if ohlcv_1m is None or len(ohlcv_1m) == 0:
            return pd.DataFrame()
        if not {"close", "volume"}.issubset(ohlcv_1m.columns):
            return pd.DataFrame()

        df = ohlcv_1m.copy()
        df.index = pd.to_datetime(df.index)

        df["ret_1m"] = df["close"].pct_change()

        min_periods = max(int(self.VOL_LOOKBACK_BARS_1M * 0.25), 1)
        df["vol_p99"] = (
            df["volume"]
            .rolling(self.VOL_LOOKBACK_BARS_1M, min_periods=min_periods)
            .quantile(self.volume_percentile / 100.0)
        )
        df["vol_pct"] = (
            df["volume"]
            .rolling(self.VOL_LOOKBACK_BARS_1M, min_periods=min_periods)
            .rank(pct=True)
        )

        # base trigger — NEGATIVE burst only
        fire = (
            (df["volume"] > df["vol_p99"])
            & (df["ret_1m"].abs() > self.magnitude_threshold)
            & (df["ret_1m"] < 0.0)
        ) & df["vol_p99"].notna()

        triggers = df[fire].copy()
        if len(triggers) == 0:
            return pd.DataFrame()

        triggers["sign"] = -1.0
        triggers["burst_z"] = triggers["ret_1m"].abs() * 100.0

        # 5m bin first-burst-sign aggregation
        bin_start = triggers.index.floor(f"{self.aggregation_bin_min}min")
        triggers["_bin"] = bin_start
        triggers = triggers.sort_index()
        first_in_bin = triggers.groupby("_bin", as_index=False).head(1).copy()
        first_in_bin = first_in_bin.drop(columns=["_bin"])

        # per-sym 30min debounce
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
        out["bnvbns_signal"] = 0.0
        out["bnvbns_burst_z"] = np.nan
        out["bnvbns_vol_pct"] = np.nan

        ohlcv_1m = self._to_1m(ctx)
        if ohlcv_1m is None or len(ohlcv_1m) == 0:
            log.warning(
                "bn_alt_volume_burst_neg_reversion_short: 1m ohlcv missing "
                "(ctx.ohlcv_1m empty and eval_freq != 1m) — emitting zero signal"
            )
            return out

        triggers = self._compute_triggers(ohlcv_1m)
        if len(triggers) == 0:
            return out

        eval_sorted = pd.DatetimeIndex(eval_idx).sort_values()
        for ts, row in triggers.iterrows():
            # 트리거를 **포함하는** 봉이 아니라 **다음** 봉에 부착한다.
            # 실행기는 봉 시가에 체결하므로(backtester `entry_price = o`,
            # orchestrator `_open_short(..., bar["open"], ...)`), 트리거를 포함하는
            # 봉에 부착하면 트리거보다 과거인 그 봉 시가에 체결된다 = lookahead.
            # 2026-08-08 실측(FILUSDT 7/1~, 43건): 트리거의 67.4%가 봉 시작 이후에
            # 발생하고 평균 1.47분 과거 가격에 체결됐다. 그 편향을 제거하면 거래당
            # 엣지가 0.7203% → 0.0175%, 승률 88.4% → 41.9% 로 무너진다 — 즉 성과
            # 전량이 이 한 줄에서 나왔다.
            # 정확히는: ts 는 1m 봉의 open_time 이라 그 봉이 닫히는 ts+1m 이후에야
            # 트리거를 알 수 있고, 체결 가능한 가장 이른 시점이 다음 eval 봉 시가다.
            pos = eval_sorted.searchsorted(ts, side="right")
            if pos < 0 or pos >= len(eval_sorted):
                continue
            bar_ts = eval_sorted[pos]
            out.loc[bar_ts, "bnvbns_signal"] = float(row["sign"])
            out.loc[bar_ts, "bnvbns_burst_z"] = float(row["burst_z"])
            out.loc[bar_ts, "bnvbns_vol_pct"] = float(row["vol_pct"])

        return out
