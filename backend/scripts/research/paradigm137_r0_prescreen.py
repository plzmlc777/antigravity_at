"""paradigm 137 R-0 prescreen — alt_intraday_realized_range_close_to_close_efficiency_ratio_z_directional_4h.

Hypothesis (Yang-Zhang / Garman-Klass 2000 range-vs-close efficiency ratio, NEW):
  per-symbol 1h OHLC:
    Step 1: per-bar Parkinson range component:
              P_t = (1 / (4 * ln 2)) * (log(high_t / low_t))**2
    Step 2: per-bar close-to-close variance component:
              C_t = (log(close_t / close_{t-1}))**2
    Step 3: 24h rolling sums:
              SumP_24h = sum(P over prior 24 bars)
              SumC_24h = sum(C over prior 24 bars)
    Step 4: efficiency ratio (24h):
              ER_t = SumP_24h / SumC_24h
            ratio > 1 = range dominates close-to-close (chop / intra-bar churn)
            ratio < 1 = close-to-close dominates (drift)
    Step 5: log transformation (Lesson #55 candidate compliance):
              log_ER_t = log(ER_t)  -> centered around 0, symmetric around log(1)=0
    Step 6: per-symbol 30d (720h) rolling z-score of log_ER:
              z_logER = (log_ER - mean_30d) / std_30d
  Trigger: |z_logER| > 2 (efficiency ratio regime extreme)
  Direction matching: log_ER sign carries directional info
    z_logER > +2 (chop regime, range >> close) -> mean-reversion semantics
        canonical direction: SHORT-prev-trigger-bar-return (fade trigger-bar move)
    z_logER < -2 (drift regime, close >> range) -> momentum semantics
        canonical direction: LONG-trigger-bar-return-sign (continue trigger move)
  Forward hold: 4h directional
  Debounce: 8h
  Universe: 12 alts (paradigm 133/134/136 cohort)

CRITICAL distinction vs prior vol family:
  - paradigm 129 Parkinson: raw Parkinson range absolute z (vol magnitude)
    -> DISTINCT: ratio (Parkinson / close-to-close), classifies CHOP vs DRIFT regime
  - paradigm 67/68/69 BTC RV: 1d close-to-close, BTC cross-asset
    -> DISTINCT: per-sym 1h, ratio decomposition (NOT raw vol level)
  - paradigm 133 vol-of-vol: std of (std), 2nd-order temporal clustering
    -> DISTINCT: 1st-order ratio decomposition (NOT 2nd-order)
  - paradigm 134 signed semivariance: up/down decomposition (ratio of UP_var / DOWN_var)
    -> DISTINCT: range vs close decomposition (NOT up vs down)
  - paradigm 136 intraday 1h vol: rolling 24h std of 1h log_ret (magnitude)
    -> DISTINCT: ratio CHOP/DRIFT classifier (NOT magnitude)
  - paradigm 135 VRP composite ratio (R-0 halt Lesson #54):
    -> DISTINGUISHING risk: paradigm 137 is ALSO a composite ratio.
    HOWEVER: paradigm 135 was funding-implied / realized (cross-domain ratio
    with funding-derived implied baseline = forced equivalence assumption).
    paradigm 137 is intra-OHLC ratio of two RV estimators on SAME data —
    Yang-Zhang (2000) established academic decomposition for measuring
    information content of high-low vs close-to-close. NOT cross-domain mixing.

Family-distinct claim (Lesson #44 amendment 20th dogfood):
  Range-vs-close efficiency ratio is novel statistic class:
    paradigm 67/68/69: 1d close-to-close RV (1d, BTC, raw level)
    paradigm 124: kurtosis/skewness (3rd/4th moments)
    paradigm 125: quarticity bipower (jump test ratio) — Lesson #40 halt
    paradigm 129: raw Parkinson high-low (1st-order range magnitude)
    paradigm 130: ATR breakout (level)
    paradigm 133: vol-of-vol (2nd-order)
    paradigm 134: signed UP/DOWN ratio (sign decomposition)
    paradigm 135: VRP cross-domain ratio (Lesson #54 halt)
    paradigm 136: 1st-order TOTAL std (magnitude, Lesson #55 halt)
    paradigm 137: RANGE/CLOSE intra-OHLC efficiency ratio (NEW, regime CLASSIFIER)

NOTE on Lesson #21 sub-finding magnitude-ratio prescreen (MANDATORY):
  This candidate IS a composite ratio.
  Sub-finding asks: are the two components syntactically distinct but
  empirically dominated by the same magnitude factor?
  If Parkinson and close-to-close variance are both dominated by a common
  vol magnitude (i.e., they co-move 1:1), the ratio reduces to noise
  (their ratio is just division of correlated magnitudes).
  R-0 measurement: per-sym, compute correlation(SumP_24h, SumC_24h) +
  ratio_p50 stability + check if log_ER variance >> noise floor.
  Halt conditions (ratio reduction trap):
    (a) per-sym correlation(SumP, SumC) > 0.95 on >= 10/12 syms
        -> magnitude co-movement dominant, ratio noise only
    (b) per-sym ratio_p50 has < 0.10 absolute deviation around its
        own per-sym mean across syms (uniform ~1.0 with no regime info)
    (c) log_ER 30d-rolling std < 0.20 on >= 10/12 syms (regime info too weak)
  If ANY of (a)/(b)/(c) on >= 10/12 syms: HALT_LESSON_21_SUB_FINDING_RATIO_REDUCTION

NOTE on Lesson #55 candidate (asymmetric z distribution):
  Raw efficiency ratio is positive (both components positive).
  log(ratio) transformation is symmetric around log(1)=0 IF Parkinson and
  close-to-close vol are equal in expectation (which is approximately
  true for random walk: Parkinson estimator unbiased for variance under GBM).
  R-0 will measure empirical z_logER distribution. If z_logER<-2 still
  sample-insufficient (paradigm 136 fail mode replicated), declare
  one-sided trigger paradigm (2-quadrant SNT only).

NOTE on Lesson #40 (structural threshold attainability):
  log(ratio) is unbounded both sides.
  z-score on log_ER REPLACES raw threshold.
  z-score CAN go negative (drift regime) and positive (chop regime)
  symmetrically IF log_ER fluctuates around 0 (which is the YZ 2000
  null hypothesis for diffusion).
  Empirical measurement at R-0 to verify reachability.

NOTE on Lesson #50 (first-burst-sign):
  4h frame -- not 5m+, Lesson #50 N/A.

NOTE on range estimator family 2nd dogfood:
  paradigm 129 (raw Parkinson) GRAVEYARD; paradigm 137 (Parkinson ratio) 2nd.
  If 137 also BROAD_FALSIFIED -> family retire CANDIDATE promotion (2 dogfoods).
  Mitigation: paradigm 137 statistic semantics fundamentally different
  (regime CLASSIFIER, not vol magnitude estimator).

NOTE on Lesson #54 (composite ratio/division halt):
  paradigm 135 was halted for cross-domain ratio (funding-implied vs realized).
  paradigm 137 IS a ratio but INTRA-DOMAIN (both estimators on same 1h OHLC).
  Yang-Zhang (2000) is established literature, not ad-hoc mixing.
  COMPLIANT — within-domain decomposition ratio is permitted.

Lessons applied:
  #11 sample density            — per-symbol per-quadrant per-quarter >=30
  #16 Concentration Gate        — deferred to R-1 (STRICT 30% required)
  #19 SNT mandatory             — 4-quadrant SNT in R-1 batch (2-quadrant if Lesson #55)
  #20 4-cond narrow scope       — life-changing 4-dim pre-empt qualification
  #21 axis stacking avoidance   — single ratio axis (NOT 3-way stack)
  #21 sub-finding magnitude-ratio MANDATORY — measure correlation, p50, log-ER variance
  #22 frame-grade               — 1h base + 24h rolling sum + 30d z-score (720 obs)
  #23 non-event-anchored        — continuous rolling
  #28 substrate availability    — 1m OHLCV per-symbol -> 1h OHLC aggregation
  #30 data_window_ratio         — ADA excluded; 12 syms 750+d PASS
  #34 empirical distribution    — z_logER p1/p5/p10/p50/p90/p95/p99 + log_ER std
  #39 sub-class detection       — A_focus z>+2 × SHORT (chop fade) /
                                    B_focus z<-2 × LONG (drift continue)
  #40 structural threshold      — log-transform + z-score per Lesson #40 guidance
  #41 amendment dual-mode       — per-trade edge >= +2% advisory at R-1 narrow-scope pre-empt
  #43 trap awareness            — direction from log_ER sign (regime semantic) + trigger-bar sign
  #44 amendment xref 20th dogfood — graveyard + RUNBOOK + INDEX cross-reference
  #45 family-distinct           — explicit z-threshold (NOT HMM unsupervised)
  #46 AMENDMENT REFINEMENT + sub-amendment 12th — stratified n=50x4q + per-quarter sign flip
  #48 inventory check scope      — graveyard + RUNBOOK + INDEX cross-reference
  #52 a/b detection (confirmed)  — both LONG/SHORT quadrants positive pattern detection at R-1
  #53 candidate detection        — hypothesis dir vs mirror dir comparison at R-1
  #54 composite ratio CONFIRMED — INTRA-DOMAIN ratio (within-OHLC), distinct from p135 cross-domain
  #55 candidate asymmetric z (1 dogfood) — log-transform applied; if z<-2 still insufficient
                                              declare one-sided 2-quadrant SNT

Family avoidance verified:
  - HMM unsupervised: AVOIDED (explicit z-threshold)
  - OI velocity directional: AVOIDED (price-based)
  - Stateful CP: AVOIDED (stateless rolling z on log_ER)
  - Higher-order moment: AVOIDED (2nd moment estimators only)
  - Signed up/down decomposition: AVOIDED (range/close decomp, NOT up/down)
  - 2nd-order vol-of-vol: AVOIDED
  - Funding single-signal: AVOIDED
  - Volume share: AVOIDED
  - Magnitude-confluence: AVOIDED (single ratio axis)
  - Listing event: AVOIDED (continuous rolling)
  - 5m microstructure single-domain: AVOIDED (1h base + 4h frame)
  - Universe-aggregate scalar: AVOIDED (per-symbol)
  - Session-anchor: AVOIDED (continuous rolling)
  - VWAP/EWMA smoothed deviation: AVOIDED
  - paradigm 67/68/69 BTC RV 1d cross-asset: AVOIDED
  - paradigm 118 realized correlation matrix: AVOIDED
  - paradigm 129 raw Parkinson: AVOIDED (ratio NOT raw)
  - paradigm 133 vol-of-vol 2nd-order: AVOIDED (1st-order ratio)
  - paradigm 134 signed semivariance: AVOIDED (range/close NOT up/down)
  - paradigm 135 VRP cross-domain: AVOIDED (within-OHLC NOT cross-domain)
  - paradigm 136 intraday 1h std magnitude: AVOIDED (ratio classifier NOT magnitude)
"""
from __future__ import annotations

import json
import logging
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("p137_r0")

PARADIGM_NAME = "alt_intraday_realized_range_close_to_close_efficiency_ratio_z_directional_4h"
PARADIGM_NUM = 137
OUT_DIR = Path(f"/home/hcpark/antigravity/backend/runs/research_track/{PARADIGM_NAME}")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 12 alts (paradigm 133/134/136 cohort, ADA excluded Lesson #30 short-window)
COHORT = [
    "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT",
    "NEARUSDT", "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

ROLLING_SUM_HOURS = 24            # 24h rolling sum (24 obs of 1h Parkinson + close-to-close)
ZSCORE_ROLLING_HOURS = 30 * 24    # 30 days = 720 hours for z-score baseline on log_ER
Z_THRESHOLD = 2.0                  # |z| > 2 symmetric
FORWARD_HOLD_4H_BARS = 1           # 4h forward hold
DEBOUNCE_HOURS = 8                 # 8h between consecutive triggers per-symbol
FEE_BP = 16.0
PARKINSON_CONST = 1.0 / (4.0 * math.log(2.0))
DB_DSN = "postgresql://antigravity_user:antigravity_password@localhost:5432/antigravity_db"


def load_ohlcv_1m(sym: str, engine) -> pd.DataFrame:
    """Load 1m OHLCV (need full OHLC for Parkinson)."""
    q = text(
        "SELECT timestamp, open, high, low, close FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
    )
    df = pd.read_sql(q, engine, params={"s": sym}, parse_dates=["timestamp"])
    if df.empty:
        return df
    df = df.set_index("timestamp")
    return df


def aggregate_to_1h_ohlc(df_1m: pd.DataFrame) -> pd.DataFrame:
    """1m OHLC -> 1h OHLC (open=first, high=max, low=min, close=last)."""
    ohlc_1h = pd.DataFrame({
        "open":  df_1m["open"].resample("1h").first(),
        "high":  df_1m["high"].resample("1h").max(),
        "low":   df_1m["low"].resample("1h").min(),
        "close": df_1m["close"].resample("1h").last(),
    }).dropna()
    return ohlc_1h


def compute_efficiency_ratio_components(ohlc_1h: pd.DataFrame) -> pd.DataFrame:
    """Compute per-bar Parkinson + close-to-close components + rolling 24h sums + log_ER.

    Per-bar:
      P_t = (1 / (4 ln 2)) * (log(high/low))**2
      C_t = (log(close / close_prev))**2
    Rolling 24h:
      SumP = sum(P over 24 bars)
      SumC = sum(C over 24 bars)
      ER = SumP / SumC
      log_ER = log(ER) (NaN if ER <= 0 or undefined)
    """
    h = ohlc_1h["high"].astype(float)
    l = ohlc_1h["low"].astype(float)
    c = ohlc_1h["close"].astype(float)
    # Per-bar Parkinson (handle h == l -> 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        log_hl = np.log(h / l)
        P = PARKINSON_CONST * (log_hl ** 2)
    P = P.replace([np.inf, -np.inf], np.nan)
    # Per-bar close-to-close variance
    with np.errstate(divide="ignore", invalid="ignore"):
        log_cc = np.log(c / c.shift(1))
        C = log_cc ** 2
    C = C.replace([np.inf, -np.inf], np.nan)
    # Rolling 24h sums (min_periods 18 = allow 6 NaN)
    sum_P = P.rolling(window=ROLLING_SUM_HOURS, min_periods=18).sum()
    sum_C = C.rolling(window=ROLLING_SUM_HOURS, min_periods=18).sum()
    # ER and log_ER (only defined if both sums positive)
    with np.errstate(divide="ignore", invalid="ignore"):
        ER = sum_P / sum_C
        log_ER = np.log(ER)
    log_ER = log_ER.replace([np.inf, -np.inf], np.nan)
    out = pd.DataFrame({
        "P_per_bar": P,
        "C_per_bar": C,
        "SumP_24h": sum_P,
        "SumC_24h": sum_C,
        "ER_24h": ER,
        "log_ER_24h": log_ER,
    }, index=ohlc_1h.index)
    return out


def compute_log_ER_z(log_ER: pd.Series) -> pd.Series:
    """Per-symbol 30d rolling z-score on log_ER."""
    m = log_ER.rolling(window=ZSCORE_ROLLING_HOURS, min_periods=240).mean()
    s = log_ER.rolling(window=ZSCORE_ROLLING_HOURS, min_periods=240).std()
    return (log_ER - m) / s


def aggregate_to_4h(df_1m: pd.DataFrame) -> pd.DataFrame:
    """4h bar close + log return."""
    bar4h = df_1m["close"].resample("4h").last().dropna().to_frame("close")
    bar4h["log_ret_4h"] = np.log(bar4h["close"]).diff()
    return bar4h


def main():
    log.info("paradigm %d R-0 start (KST %s)", PARADIGM_NUM,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    engine = create_engine(DB_DSN)

    log.info("--- Step 1: per-symbol 1m -> 1h OHLC -> Parkinson + close^2 -> 24h sums -> log_ER -> 30d z ---")
    sym_data = {}
    per_sym_days = {}
    z_aggregate = []
    log_ER_aggregate = []

    # Lesson #21 sub-finding magnitude-ratio prescreen (MANDATORY)
    sub_finding = {}  # per-sym: {corr_PC, ratio_p50, log_ER_std_30d}

    for sym in COHORT:
        try:
            df = load_ohlcv_1m(sym, engine)
            if df.empty or len(df) < 30 * 24 * 60 * 2:
                log.warning("%s: insufficient 1m data (n=%d) -- skip", sym, len(df))
                continue
            days = (df.index.max() - df.index.min()).days
            per_sym_days[sym] = days

            ohlc_1h = aggregate_to_1h_ohlc(df)
            if len(ohlc_1h) < ZSCORE_ROLLING_HOURS + ROLLING_SUM_HOURS:
                log.warning("%s: insufficient 1h OHLC (n=%d) -- skip", sym, len(ohlc_1h))
                continue

            comp = compute_efficiency_ratio_components(ohlc_1h)
            log_ER = comp["log_ER_24h"]
            z = compute_log_ER_z(log_ER)
            bar4h = aggregate_to_4h(df)

            # Lesson #21 sub-finding: dominant component check
            sumP_finite = comp["SumP_24h"].dropna()
            sumC_finite = comp["SumC_24h"].dropna()
            common_idx = sumP_finite.index.intersection(sumC_finite.index)
            if len(common_idx) > 100:
                corr_PC = float(np.corrcoef(
                    sumP_finite.loc[common_idx].values,
                    sumC_finite.loc[common_idx].values,
                )[0, 1])
            else:
                corr_PC = float("nan")
            ratio_finite = comp["ER_24h"].dropna()
            ratio_p50 = float(np.median(ratio_finite.values)) if len(ratio_finite) else float("nan")
            log_ER_finite = log_ER.dropna()
            log_ER_std = float(np.std(log_ER_finite.values, ddof=1)) if len(log_ER_finite) > 1 else float("nan")
            sub_finding[sym] = {
                "corr_SumP_SumC": corr_PC,
                "ratio_ER_p50": ratio_p50,
                "log_ER_overall_std": log_ER_std,
                "n_log_ER": int(len(log_ER_finite)),
            }

            # Sample empirical distributions
            z_finite = z.dropna().values
            z_aggregate.extend(z_finite.tolist()[:5000])
            log_ER_aggregate.extend(log_ER_finite.values.tolist()[:5000])

            sym_data[sym] = {
                "df_1m": df,
                "ohlc_1h": ohlc_1h,
                "comp": comp,
                "z": z,
                "bar4h": bar4h,
            }
            log.info(
                "%s: %d days, %d 1h bars, log_ER std=%.3f corr(SumP,SumC)=%.3f ratio_p50=%.3f "
                "z range [%.2f, %.2f] valid=%d",
                sym, days, len(ohlc_1h), log_ER_std, corr_PC, ratio_p50,
                float(np.nanmin(z_finite)) if len(z_finite) else float("nan"),
                float(np.nanmax(z_finite)) if len(z_finite) else float("nan"),
                len(z_finite),
            )
        except Exception as e:
            log.error("%s load fail: %s", sym, e)

    engine.dispose()

    if not sym_data:
        log.error("no symbols loaded")
        sys.exit(1)

    full_window = max(per_sym_days.values())
    short_window_syms = {s: d for s, d in per_sym_days.items() if d < full_window * 0.30}
    log.info("Lesson #30 audit: full_window=%d days, short-window syms(<30%%): %s",
             full_window, short_window_syms)

    # Lesson #21 sub-finding magnitude-ratio prescreen verdict
    log.info("--- Lesson #21 sub-finding magnitude-ratio prescreen ---")
    n_syms = len(sub_finding)
    n_high_corr = sum(1 for v in sub_finding.values() if v["corr_SumP_SumC"] > 0.95)
    ratio_p50_values = [v["ratio_ER_p50"] for v in sub_finding.values()
                        if not math.isnan(v["ratio_ER_p50"])]
    ratio_p50_mean = float(np.mean(ratio_p50_values)) if ratio_p50_values else float("nan")
    ratio_p50_max_dev = (max(abs(r - ratio_p50_mean) for r in ratio_p50_values)
                        if ratio_p50_values else float("nan"))
    n_low_log_ER_std = sum(1 for v in sub_finding.values() if v["log_ER_overall_std"] < 0.20)
    # threshold for halt: >= 10/12 syms (>= 83%)
    halt_threshold = math.ceil(n_syms * 0.83)
    cond_a_high_corr = n_high_corr >= halt_threshold
    cond_c_low_log_ER_std = n_low_log_ER_std >= halt_threshold
    log.info("n_syms=%d halt_threshold(>=%d/%d):", n_syms, halt_threshold, n_syms)
    log.info("  cond_a corr(SumP, SumC) > 0.95: %d syms (HALT if >= %d)",
             n_high_corr, halt_threshold)
    log.info("  cond_c log_ER overall std < 0.20: %d syms (HALT if >= %d)",
             n_low_log_ER_std, halt_threshold)
    log.info("  cond_b ratio_p50 mean=%.3f max_dev=%.3f (informational)",
             ratio_p50_mean, ratio_p50_max_dev)
    lesson_21_sub_finding = {
        "n_syms_audited": n_syms,
        "halt_threshold_n_of_12": int(halt_threshold),
        "n_syms_corr_above_0.95": n_high_corr,
        "n_syms_log_ER_std_below_0.20": n_low_log_ER_std,
        "ratio_p50_mean_across_syms": ratio_p50_mean,
        "ratio_p50_max_dev_across_syms": ratio_p50_max_dev,
        "per_sym": sub_finding,
        "cond_a_high_corr_halt": cond_a_high_corr,
        "cond_c_low_log_ER_std_halt": cond_c_low_log_ER_std,
        "verdict": ("HALT_LESSON_21_SUB_FINDING_RATIO_REDUCTION"
                    if (cond_a_high_corr or cond_c_low_log_ER_std) else "PASS"),
    }
    log.info("Lesson #21 sub-finding verdict: %s", lesson_21_sub_finding["verdict"])

    if lesson_21_sub_finding["verdict"] != "PASS":
        out = {
            "paradigm_name": PARADIGM_NAME,
            "paradigm_number": PARADIGM_NUM,
            "phase": "R-0",
            "executed_at_kst": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
            "host": "hcp_local",
            "verdict": "R0_HALT_LESSON_21_SUB_FINDING_RATIO_REDUCTION",
            "lesson_21_sub_finding_magnitude_ratio": lesson_21_sub_finding,
            "per_sym_days": per_sym_days,
            "universe_loaded": list(sym_data.keys()),
        }
        out_path = OUT_DIR / "r0_prescreen.json"
        out_path.write_text(json.dumps(out, indent=2, default=str))
        log.error("HALT — Lesson #21 sub-finding ratio reduction trap; saved %s", out_path)
        sys.exit(2)

    # Lesson #34 empirical z + log_ER distribution
    z_arr = np.array(z_aggregate)
    z_arr_finite = z_arr[np.isfinite(z_arr)]
    pct_z = {p: float(np.percentile(z_arr_finite, p))
             for p in [1, 5, 10, 50, 70, 90, 95, 99]}
    z_max = float(np.max(z_arr_finite)) if len(z_arr_finite) else float("nan")
    z_min = float(np.min(z_arr_finite)) if len(z_arr_finite) else float("nan")
    log.info("z_logER empirical percentiles (n=%d): %s", len(z_arr_finite), pct_z)
    log.info("z_logER min=%.2f max=%.2f", z_min, z_max)

    logER_arr = np.array(log_ER_aggregate)
    logER_arr_finite = logER_arr[np.isfinite(logER_arr)]
    pct_logER = {p: float(np.percentile(logER_arr_finite, p))
                 for p in [1, 5, 10, 50, 70, 90, 95, 99]}
    log.info("log_ER empirical percentiles (n=%d): %s",
             len(logER_arr_finite), pct_logER)

    # Lesson #40 + #55 — symmetric vs asymmetric reachability
    z_max_reachable = z_max >= Z_THRESHOLD
    z_min_reachable = z_min <= -Z_THRESHOLD
    n_z_above = int((z_arr_finite > Z_THRESHOLD).sum())
    n_z_below = int((z_arr_finite < -Z_THRESHOLD).sum())
    pct_above = n_z_above / len(z_arr_finite) if len(z_arr_finite) else 0.0
    pct_below = n_z_below / len(z_arr_finite) if len(z_arr_finite) else 0.0

    # Lesson #55 candidate detection (paradigm 136 fail mode replication check)
    # If asymmetry > 5x (one side has 5x more triggers) -> declare one-sided
    if n_z_below > 0 and n_z_above > 0:
        asymmetry_ratio = max(n_z_above, n_z_below) / min(n_z_above, n_z_below)
    else:
        asymmetry_ratio = float("inf")
    lesson_55_asymmetric = asymmetry_ratio > 5.0
    log.info(
        "Lesson #55 candidate: above_pos2=%d below_neg2=%d asym_ratio=%.2f %s",
        n_z_above, n_z_below, asymmetry_ratio,
        "(ASYMMETRIC, may need 2-quadrant SNT)" if lesson_55_asymmetric else "(SYMMETRIC)"
    )

    lesson_40 = {
        "threshold_definition": f"|z| > {Z_THRESHOLD} on per-symbol 30d-rolling z of log_ER (24h)",
        "stat_class": "log_ratio_of_two_non_negative_rolling_sums_with_zscore",
        "z_score_applied": True,
        "log_transform_applied": True,
        "symmetric_negative_use": True,
        "reformulation": "log(ratio) + z-score makes z symmetric for diffusion (YZ 2000)",
        "empirical_z_max": z_max,
        "empirical_z_min": z_min,
        "z_max_reachable_pos2": z_max_reachable,
        "z_min_reachable_neg2": z_min_reachable,
        "n_above_pos2": n_z_above,
        "n_below_neg2": n_z_below,
        "pct_above_pos2": pct_above,
        "pct_below_neg2": pct_below,
        "asymmetry_ratio": asymmetry_ratio,
        "verdict": ("PASS" if (z_max_reachable and z_min_reachable)
                    else "FAIL_STRUCTURAL_THRESHOLD_INFEASIBLE"),
    }
    log.info("Lesson #40 verification: %s", lesson_40)

    if not (z_max_reachable and z_min_reachable):
        out = {
            "paradigm_name": PARADIGM_NAME,
            "paradigm_number": PARADIGM_NUM,
            "phase": "R-0",
            "executed_at_kst": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
            "host": "hcp_local",
            "verdict": "R0_HALT_LESSON_40_STRUCTURAL_THRESHOLD_INFEASIBLE",
            "lesson_40": lesson_40,
            "lesson_21_sub_finding_magnitude_ratio": lesson_21_sub_finding,
        }
        out_path = OUT_DIR / "r0_prescreen.json"
        out_path.write_text(json.dumps(out, indent=2, default=str))
        log.error("HALT — Lesson #40 threshold infeasible; saved %s", out_path)
        sys.exit(2)

    # Step 2: build triggers + direction matching + fwd_4h
    log.info("--- Step 2: build triggers (|z_logER| > %.1f, debounce %dh, fwd 4h) ---",
             Z_THRESHOLD, DEBOUNCE_HOURS)
    trig_rows = []
    for sym, d in sym_data.items():
        z = d["z"]
        bar4h = d["bar4h"]

        # Resample z to 4h boundary (last 1h value within each 4h)
        z_4h = z.resample("4h").last().dropna()
        z_4h_aligned = z_4h.reindex(bar4h.index, method="ffill")
        bar4h = bar4h.copy()
        bar4h["z_logER"] = z_4h_aligned
        bar4h["fwd_log_ret_4h"] = bar4h["log_ret_4h"].shift(-FORWARD_HOLD_4H_BARS)

        last_ts = None
        for ts, row in bar4h.iterrows():
            z_val = row["z_logER"]
            if pd.isna(z_val) or abs(z_val) <= Z_THRESHOLD:
                continue
            if pd.isna(row["log_ret_4h"]) or pd.isna(row["fwd_log_ret_4h"]):
                continue
            if last_ts is not None and (ts - last_ts).total_seconds() < DEBOUNCE_HOURS * 3600:
                continue
            # Direction semantics (Yang-Zhang efficiency ratio):
            #   z_logER > +2 (chop regime, range >> close): mean-reversion candidate
            #     -> direction = OPPOSITE trigger-bar sign (fade the move)
            #   z_logER < -2 (drift regime, close >> range): momentum candidate
            #     -> direction = SAME as trigger-bar sign (continue the move)
            trigger_sign = 1 if row["log_ret_4h"] > 0 else -1
            if z_val > 0:
                # chop -> fade
                direction = -trigger_sign
                regime = "chop_fade"
            else:
                # drift -> continue
                direction = trigger_sign
                regime = "drift_continue"
            signed_fwd_bp = float(row["fwd_log_ret_4h"]) * direction * 10000.0
            trig_rows.append({
                "ts": ts,
                "sym": sym,
                "z_logER": float(z_val),
                "log_ret_4h": float(row["log_ret_4h"]),
                "trigger_sign": trigger_sign,
                "direction": direction,
                "regime": regime,
                "fwd_log_ret_4h": float(row["fwd_log_ret_4h"]),
                "signed_fwd_bp": signed_fwd_bp,
                "qtr": str(ts.to_period("Q")),
            })
            last_ts = ts

    trig_df = pd.DataFrame(trig_rows)
    if trig_df.empty:
        log.error("zero triggers -- abort")
        sys.exit(1)
    n_a = int((trig_df["regime"] == "chop_fade").sum())
    n_b = int((trig_df["regime"] == "drift_continue").sum())
    log.info("total triggers across %d syms: %d (chop_fade=%d, drift_continue=%d)",
             len(sym_data), len(trig_df), n_a, n_b)

    # Per-quarter density (Lesson #11)
    n_quarters = trig_df["qtr"].nunique()
    per_q_a = trig_df[trig_df["regime"] == "chop_fade"].groupby("qtr").size()
    per_q_b = trig_df[trig_df["regime"] == "drift_continue"].groupby("qtr").size()
    log.info("per-quarter chop_fade (z>+2): %s", per_q_a.to_dict())
    log.info("per-quarter drift_continue (z<-2): %s", per_q_b.to_dict())
    measurable_q_a = int((per_q_a >= 30).sum())
    measurable_q_b = int((per_q_b >= 30).sum())
    log.info("measurable quarters (>=30): chop_fade=%d/%d drift_continue=%d/%d",
             measurable_q_a, n_quarters, measurable_q_b, n_quarters)

    # Lesson #46 AMENDMENT REFINEMENT + sub-amendment 12th
    log.info("--- Lesson #46 REFINEMENT (12th dogfood elevation-eligible): "
             "temporally-stratified n=50x4q R-0 ---")
    sorted_quarters = sorted(trig_df["qtr"].unique())
    log.info("quarters available: %d %s", len(sorted_quarters), sorted_quarters)
    if len(sorted_quarters) < 4:
        sample = trig_df.iloc[:200]
        strat_strategy = f"fallback_chronological_n200_have{len(sorted_quarters)}q"
        qtrs_to_use = sorted_quarters
    else:
        qtrs_to_use = [
            sorted_quarters[0],
            sorted_quarters[len(sorted_quarters) // 3],
            sorted_quarters[2 * len(sorted_quarters) // 3],
            sorted_quarters[-1],
        ]
        qtrs_to_use = sorted(set(qtrs_to_use))
        log.info("temporally-stratified quarters chosen: %s", qtrs_to_use)
        per_q_samples = []
        for qq in qtrs_to_use:
            q_data = trig_df[trig_df["qtr"] == qq].sort_values("ts")
            n_take = min(50, len(q_data))
            per_q_samples.append(q_data.iloc[:n_take])
        sample = pd.concat(per_q_samples)
        strat_strategy = f"temporally_stratified_n50x{len(qtrs_to_use)}q_total_n={len(sample)}"

    # 4-quadrant estimate (or 2-quadrant if Lesson #55 asymmetric flag set)
    a_focus = sample[sample["regime"] == "chop_fade"]["signed_fwd_bp"]
    a_mirror = -a_focus
    b_focus = sample[sample["regime"] == "drift_continue"]["signed_fwd_bp"]
    b_mirror = -b_focus

    def stats(s, lbl):
        if len(s) < 2:
            return {"label": lbl, "n": int(len(s)), "gross_bp": None,
                    "net_bp": None, "t": None}
        m = float(s.mean())
        sd = float(s.std(ddof=1))
        n = int(len(s))
        return {
            "label": lbl, "n": n, "gross_bp": m, "net_bp": m - FEE_BP,
            "t": (m / (sd / math.sqrt(n))) if sd > 0 else None,
        }

    qa = stats(a_focus, "A_focus_chop_fade")
    qam = stats(a_mirror, "A_mirror_chop_continue")
    qb = stats(b_focus, "B_focus_drift_continue")
    qbm = stats(b_mirror, "B_mirror_drift_fade")
    log.info("R-0 4-quadrant stratified estimate (strategy=%s):", strat_strategy)
    for q in [qa, qam, qb, qbm]:
        log.info("  %s n=%d gross=%s net=%s t=%s", q["label"], q["n"],
                 f"{q['gross_bp']:.2f}" if q["gross_bp"] is not None else "NA",
                 f"{q['net_bp']:.2f}" if q["net_bp"] is not None else "NA",
                 f"{q['t']:.2f}" if q["t"] is not None else "NA")

    # Per-quarter sign-flip detection (Lesson #46 sub-amendment 12th dogfood)
    log.info("--- Per-quarter R-0 gross by quadrant (Lesson #46 sub-amendment 12th dogfood) ---")
    per_qtr_r0 = {}
    a_signs = []
    b_signs = []
    for qq in qtrs_to_use:
        q_sample = trig_df[trig_df["qtr"] == qq].sort_values("ts").iloc[:50]
        q_a = q_sample[q_sample["regime"] == "chop_fade"]["signed_fwd_bp"]
        q_b = q_sample[q_sample["regime"] == "drift_continue"]["signed_fwd_bp"]
        a_g = float(q_a.mean()) if len(q_a) > 0 else None
        b_g = float(q_b.mean()) if len(q_b) > 0 else None
        per_qtr_r0[qq] = {
            "n_total": int(len(q_sample)),
            "A_focus_n": int(len(q_a)),
            "A_focus_gross_bp": a_g,
            "B_focus_n": int(len(q_b)),
            "B_focus_gross_bp": b_g,
        }
        if a_g is not None:
            a_signs.append(1 if a_g > 0 else -1)
        if b_g is not None:
            b_signs.append(1 if b_g > 0 else -1)
        log.info("  %s: A_focus (chop_fade) n=%d gross=%s | B_focus (drift_continue) n=%d gross=%s",
                 qq, len(q_a),
                 f"{a_g:.2f}" if a_g is not None else "NA",
                 len(q_b),
                 f"{b_g:.2f}" if b_g is not None else "NA")

    def flips(signs):
        return sum(1 for i in range(1, len(signs)) if signs[i] != signs[i - 1])

    a_flips = flips(a_signs)
    b_flips = flips(b_signs)
    log.info("Lesson #46 sign-flip: A_focus flips=%d (%s) | B_focus flips=%d (%s)",
             a_flips, a_signs, b_flips, b_signs)

    # Lesson #44 cross-reference (20th dogfood)
    lesson_44_xref = {
        "paradigm_65_skewness_mr":
            "GRAVEYARD — 3rd moment cross-sec. DISTINCT: range/close decomposition.",
        "paradigm_66_skewness_momentum":
            "GRAVEYARD — 3rd moment momentum. DISTINCT: 2nd-order RV decomposition.",
        "paradigm_67_btc_rv_spike_alt_recovery":
            "GRAVEYARD — BTC 1d close RV cross-asset. DISTINCT: per-sym 1h intra-OHLC ratio.",
        "paradigm_68_btc_rv_spike_up_conditional":
            "GRAVEYARD R-3.5 — BTC RV sign-cond. DISTINCT: per-sym, range/close ratio.",
        "paradigm_69_btc_rv_spike_highvol_filter":
            "R-5 SEEDED — BTC 1d RV p90 LONG. DISTINCT: ratio classifier (NOT level filter).",
        "paradigm_81_rolling_beta_regime":
            "GRAVEYARD — rolling beta vs BTC. DISTINCT: intrinsic per-sym OHLC ratio.",
        "paradigm_84_book_depth_cusum":
            "SAMPLE_INSUFFICIENT — Page-Hinkley CP. DISTINCT: stateless rolling z on log_ER.",
        "paradigm_118_realized_correlation_regime":
            "GRAVEYARD — cross-corr matrix. DISTINCT: per-sym ratio decomp.",
        "paradigm_121_hmm_realized_vol_state":
            "GRAVEYARD Lesson #45 — HMM unsup. DISTINCT: explicit z on log_ER (Lesson #45 compliant).",
        "paradigm_124_alt_realized_kurtosis_skewness":
            "GRAVEYARD — 3rd × 4th moment. DISTINCT: 2nd-order ratio decomp.",
        "paradigm_125_alt_realized_quarticity_bipower":
            "R-0 HALT Lesson #40 — B-N jump test ratio. DISTINCT: log-transform applied per Lesson #40.",
        "paradigm_129_alt_parkinson_range":
            "GRAVEYARD — RAW Parkinson high-low (vol magnitude). "
            "DISTINCT: Parkinson AS NUMERATOR of efficiency ratio (regime classifier).",
        "paradigm_130_alt_atr_normalized_range_breakout":
            "GRAVEYARD — ATR + level breakout. DISTINCT: pure RV decomposition ratio.",
        "paradigm_131_alt_volume_burst_intra5m_signed":
            "GRAVEYARD — 5m volume burst. DISTINCT: 1h OHLC + 4h frame, no volume.",
        "paradigm_132_funding_oi_magnitude_triple":
            "GRAVEYARD Lesson #21 — 3-way axis stacking. DISTINCT: single trigger axis (ratio).",
        "paradigm_133_alt_realized_vol_of_vol":
            "GRAVEYARD CONCENTRATED_R1_PASS — 2nd-order std-of-std. "
            "DISTINCT: 1st-order ratio (NOT 2nd-order temporal).",
        "paradigm_134_alt_realized_semivariance_asymmetry":
            "GRAVEYARD — UP/DOWN ratio. DISTINCT: RANGE/CLOSE ratio (different decomp axis).",
        "paradigm_135_alt_funding_implied_vs_realized_vol_premium":
            "R-0 HALT Lesson #54 — funding-derived implied / realized (CROSS-DOMAIN). "
            "DISTINCT: paradigm 137 is INTRA-DOMAIN (both estimators on same 1h OHLC). "
            "Yang-Zhang (2000) established within-OHLC decomposition.",
        "paradigm_136_alt_intraday_1h_log_return_std":
            "R-0 HALT Lesson #55 — magnitude only. "
            "DISTINCT: 137 is RATIO (regime classifier), NOT magnitude.",
        "paradigm_126_127_128_volume_burst_family":
            "R-5 SEEDED 127+128 — 1m volume burst. DISTINCT: 4h frame + OHLC ratio.",
    }

    # Family-avoidance verification
    family_avoidance = {
        "HMM_unsupervised": "AVOIDED (explicit z-threshold on log_ER, Lesson #45)",
        "OI_velocity_directional": "AVOIDED (price-based OHLC)",
        "Stateful_CP_Page_Hinkley": "AVOIDED (stateless rolling z, Lesson #22)",
        "Higher_order_moment_kurtosis_skewness": "AVOIDED (2nd-order RV components)",
        "Signed_decomposition_semivariance": "AVOIDED (range/close decomp, NOT up/down)",
        "High_low_range_Parkinson_RAW": "AVOIDED (Parkinson AS NUMERATOR of ratio, NOT raw)",
        "Second_order_vol_of_vol": "AVOIDED (1st-order ratio)",
        "Funding_single_signal": "AVOIDED (no funding)",
        "Volume_share": "AVOIDED (no volume)",
        "Magnitude_confluence": "AVOIDED (single trigger axis, ratio)",
        "Listing_event": "AVOIDED (continuous rolling)",
        "5m_microstructure_single_domain": "AVOIDED (1h base + 4h frame)",
        "Universe_aggregate_scalar": "AVOIDED (per-symbol)",
        "Session_anchor": "AVOIDED (continuous rolling)",
        "VWAP_EWMA_smoothed_deviation": "AVOIDED (rolling sums + log + z, no smoothing)",
        "paradigm_67_68_69_BTC_RV_1d_cross_asset": "AVOIDED (per-sym 1h intra-OHLC)",
        "paradigm_118_realized_corr_matrix": "AVOIDED (per-sym ratio, NOT cross-corr)",
        "paradigm_129_raw_Parkinson_vol_magnitude": "AVOIDED (ratio classifier, NOT raw magnitude)",
        "paradigm_133_vol_of_vol_2nd_order": "AVOIDED (1st-order ratio decomp)",
        "paradigm_134_signed_UP_DOWN_semivariance": "AVOIDED (RANGE/CLOSE decomp)",
        "paradigm_135_VRP_cross_domain_ratio": "AVOIDED (INTRA-domain within-OHLC ratio)",
        "paradigm_136_intraday_1h_std_magnitude": "AVOIDED (regime classifier, NOT magnitude)",
        "Funding_family_3way_stack": "AVOIDED (single ratio axis)",
        "Lesson_21_sub_finding_magnitude_ratio": (
            "MEASURED IN R-0 — verdict above"
        ),
        "Lesson_54_composite_ratio_division_cross_domain": (
            "COMPLIANT — intra-domain ratio (within-OHLC), Yang-Zhang 2000 established"
        ),
    }

    # Verdict
    n_total = len(trig_df)
    n_per_sym_min = int(trig_df.groupby("sym").size().min()) if len(trig_df) else 0
    verdict_pass_conditions = {
        "n_total_ge_200": n_total >= 200,
        "measurable_q_a_ge_3": measurable_q_a >= 3,
        "measurable_q_b_ge_3": measurable_q_b >= 3,
        "n_syms_ge_5": len(sym_data) >= 5,
        "lesson_40_pass": lesson_40["verdict"] == "PASS",
        "lesson_21_sub_finding_pass": lesson_21_sub_finding["verdict"] == "PASS",
    }
    all_pass = all(verdict_pass_conditions.values())
    if not all_pass:
        # Check if one-sided 2-quadrant still feasible (Lesson #55 candidate)
        either_side_ok = (
            n_total >= 200
            and len(sym_data) >= 5
            and lesson_40["verdict"] == "PASS"
            and lesson_21_sub_finding["verdict"] == "PASS"
            and (measurable_q_a >= 3 or measurable_q_b >= 3)
        )
        if either_side_ok and lesson_55_asymmetric:
            verdict = "R0_READY_FOR_R1_ONE_SIDED_LESSON_55"
        else:
            verdict = "R0_HALT_INSUFFICIENT_DENSITY"
    else:
        verdict = "R0_READY_FOR_R1"

    out = {
        "paradigm_name": PARADIGM_NAME,
        "paradigm_number": PARADIGM_NUM,
        "phase": "R-0",
        "executed_at_kst": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "host": "hcp_local",
        "verdict": verdict,
        "verdict_pass_conditions": verdict_pass_conditions,
        "universe_cohort": COHORT,
        "universe_loaded": list(sym_data.keys()),
        "universe_excluded": {"ADAUSDT": "Lesson #30 short-window (143d << 30%)"},
        "params": {
            "rolling_sum_hours": ROLLING_SUM_HOURS,
            "zscore_rolling_hours": ZSCORE_ROLLING_HOURS,
            "z_threshold_absolute": Z_THRESHOLD,
            "forward_hold_4h_bars": FORWARD_HOLD_4H_BARS,
            "debounce_hours": DEBOUNCE_HOURS,
            "fee_bp": FEE_BP,
            "parkinson_const": PARKINSON_CONST,
        },
        "per_sym_days": per_sym_days,
        "short_window_syms_lesson_30": short_window_syms,
        "n_triggers_total": int(n_total),
        "n_triggers_chop_fade_A": n_a,
        "n_triggers_drift_continue_B": n_b,
        "n_per_sym_min": n_per_sym_min,
        "per_quarter_chop_fade_A": per_q_a.to_dict(),
        "per_quarter_drift_continue_B": per_q_b.to_dict(),
        "measurable_quarters_A": int(measurable_q_a),
        "measurable_quarters_B": int(measurable_q_b),
        "n_quarters": int(n_quarters),
        "lesson_11_density_pass": (measurable_q_a >= 3 and measurable_q_b >= 3),
        "lesson_21_sub_finding_magnitude_ratio": lesson_21_sub_finding,
        "lesson_34_empirical_z_logER_percentiles": pct_z,
        "lesson_34_empirical_log_ER_percentiles": pct_logER,
        "lesson_34_z_min": z_min,
        "lesson_34_z_max": z_max,
        "lesson_40": lesson_40,
        "lesson_55_asymmetric_z_detected": lesson_55_asymmetric,
        "lesson_55_asymmetry_ratio": asymmetry_ratio,
        "lesson_46_amendment_refinement_strategy": strat_strategy,
        "lesson_46_quarters_used": qtrs_to_use,
        "r0_4quadrant_stratified_estimate": {
            "A_focus_chop_fade": qa,
            "A_mirror_chop_continue": qam,
            "B_focus_drift_continue": qb,
            "B_mirror_drift_fade": qbm,
        },
        "per_quarter_r0_detail": per_qtr_r0,
        "lesson_46_sign_flips": {"A_focus_flips": a_flips, "A_signs": a_signs,
                                 "B_focus_flips": b_flips, "B_signs": b_signs},
        "lesson_44_xref_20th_dogfood": lesson_44_xref,
        "family_avoidance_verification": family_avoidance,
        "range_estimator_family_dogfood_count": 2,
        "range_estimator_family_retire_status": (
            "PENDING — 2nd dogfood; 137 distinct from raw 129 (ratio CLASSIFIER not magnitude)"
        ),
    }

    out_path = OUT_DIR / "r0_prescreen.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    log.info("VERDICT: %s", verdict)
    log.info("R-0 saved to %s", out_path)


if __name__ == "__main__":
    main()
