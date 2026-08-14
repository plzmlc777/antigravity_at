"""paradigm 202 R-1 — Lesson #55 candidate 1st explicit dogfood.

Hypothesis (one-sided right-tail LONG-only directional):
  Per-symbol 1h log_ret rolling 24h std (intraday vol) -> per-sym 30d (720h) z-score
  Right-tail trigger: z_vol >= +2 (HIGH vol regime, no z<-2 left-tail per Lesson #40+#55)
  Direction: LONG continuation only (no 4-quadrant SNT, asymmetric structure honor)
  Forward hold: 4h primary + 8h + 12h sweep
  Debounce: 8h
  Universe: 20 alts paradigm 198 cohort minus Lesson #30 short-window violations
             (BTC 142d, ADA 143d <30% full window 799d -> EXCLUDED)
             -> 18 syms effective

Lesson #55 candidate 1st explicit dogfood:
  paradigm 136 graveyard prescription COMPLIANT:
   - non-negative aggregate (std) asymmetric z distribution -> declare single-direction at R-0
   - z>=+2 right-tail trigger ONLY (no symmetric |z|>=2)
   - LONG continuation only (no A_mirror, no B-side)
   - SNT 4-quadrant skip (single-direction asymmetric statistic structure)

paradigm 136 baseline direct comparison MANDATORY:
  paradigm 136 R-0 stratified A_focus (z>+2, LONG, 4h):
    2024Q1: +267bp / 2024Q4: +33.83bp / 2025Q3: +68.92bp / 2026Q2: +1.34bp
    Decay 200x (2024Q1 -> 2026Q2)
  paradigm 202 R-1 verifies via 9-quarter per-quarter measurement:
    - If 2026 era (Q1+Q2) sigex > 2.0 -> paradigm 136 decay = mis-diagnosis (variance regime)
    - If 2026 era sigex < 2.0 -> paradigm 136 decay = confirmed universal alpha decay
      -> RV intraday family Tier 4 retire formal trigger

Lesson cross-reference:
  #11 sample density        - 18 syms x 2.25yr x ~4.16% trigger rate /4q = ~165 per cell PASS
  #16 Concentration Gate    - per-quarter t + per-symbol bootstrap (CI lower>0)
  #19 SNT 4-quadrant        - WAIVED per Lesson #55 (one-sided asymmetric statistic)
  #20 narrow scope          - life-changing 4-dim audit at R-1
  #21 axis stacking         - single statistic (rolling std z), single direction
  #22 frame-grade           - 1h base + 24h std (24 obs) + 30d z (720 obs)
  #23 non-event-anchored    - continuous rolling
  #28 substrate availability - 1m OHLCV DB per-sym -> 1h aggregation (paradigm 136 same)
  #30 data_window_ratio     - BTC 142d + ADA 143d EXCLUDED, 18/20 PASS
  #34 empirical distribution - z_vol empirical p99/max already validated paradigm 136
  #40 structural threshold  - z-score one-sided right-tail z>=+2 reachable (paradigm 136 p99=+4.14, max=+8.24)
  #42 NOT applicable         - LONG-only single-direction, no capitulation MR
  #44 amendment xref         - paradigm 136 prior R-0 HALT predecessor + 19 paradigms
  #45 family-distinct        - explicit z (NOT HMM), per-sym 1h (NOT BTC 1d cross-asset)
  #46 amendment refinement   - per-quarter sign-flip detection 9 quarters
  #55 candidate 1st explicit dogfood - prescription compliant verification

Lesson #62 family-distinct vs paradigm 136 (R-0 HALT):
  - statistic: IDENTICAL
  - frame: IDENTICAL
  - trigger threshold: IDENTICAL (|z|=2 magnitude, z>+2 right-tail subset)
  - universe: EXPANDED (12 -> 18, +6 syms)
  - direction class: SHIFT (bilateral 4-quad -> one-sided LONG-only)
  - hold: IDENTICAL (4h primary)
  -> 4/5 strict distinct (direction class shift per paradigm 184 precedent)

Lesson #70 corollary scope verdict: (b) direction class shift NEW paradigm class.
  paradigm 184 precedent (long-short balanced -> directional shift).
  paradigm 202 = paradigm 136 direction class shift (bilateral 4-quad -> one-sided LONG-only).
  PROCEED.

R-1 measurements:
  1. Substrate verification 18 syms 1m -> 1h aggregation
  2. Per-sym 24h rolling std of 1h log-return + 30d z-score
  3. Right-tail z>=+2 LONG continuation trigger
  4. Three-gate: sigex>=2.0 AND ci_lower>0 AND perm_p<=0.10
  5. Concentration: per-quarter t (9 quarters) + per-symbol bootstrap (18 syms)
  6. Hold sweep: 4h primary + 8h + 12h
  7. Temporal stratify: per-quarter sigex/edge/sharpe + 2024/2025/2026 era
  8. paradigm 136 baseline direct compare (2024Q1 +267bp -> 2026Q2 ?)
  9. Life-changing 4-dim audit (trades/yr/edge/util/sharpe)
"""
from __future__ import annotations

import json
import logging
import math
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

sys.path.insert(0, "/home/hcpark/antigravity/backend")
from scripts.research._perm_utils import fee_aware_perm_test, bootstrap_ci  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("p202_r1")

PARADIGM_NAME = (
    "alt_per_sym_intraday_1h_log_return_std_24h_rolling_window_z_one_sided_"
    "right_tail_z_ge_2_long_only_temporal_stratified_directional_4h"
)
PARADIGM_NUM = 202
OUT_DIR = Path(f"/home/hcpark/antigravity/backend/runs/research_track/{PARADIGM_NAME}")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 20-sym paradigm 198 cohort minus Lesson #30 short-window
COHORT_FULL = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT",
    "ADAUSDT", "AVAXUSDT", "LINKUSDT", "LTCUSDT", "BCHUSDT", "NEARUSDT",
    "FILUSDT", "WIFUSDT", "DOTUSDT", "LDOUSDT", "UNIUSDT", "ETCUSDT",
    "WLDUSDT", "JUPUSDT",
]
LESSON_30_EXCLUDED = {
    "BTCUSDT": "Lesson #30 short-window (142d / 799d full = 17.8% << 30%)",
    "ADAUSDT": "Lesson #30 short-window (143d / 799d full = 17.9% << 30%)",
}

VOL_ROLLING_HOURS = 24
ZSCORE_ROLLING_HOURS = 30 * 24
Z_THRESHOLD = 2.0  # one-sided right-tail (z >= +Z_THRESHOLD)
HOLD_BARS = {"4h": 1, "8h": 2, "12h": 3}
PRIMARY_HOLD = "4h"
DEBOUNCE_HOURS = 8
FEE_RT = 0.0016  # 16bp round-trip
DB_DSN = "postgresql://antigravity_user:antigravity_password@localhost:5432/antigravity_db"


def load_ohlcv_1m(sym: str, engine) -> pd.DataFrame:
    """Load 1m OHLCV from DB."""
    q = text(
        "SELECT timestamp, close FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
    )
    df = pd.read_sql(q, engine, params={"s": sym}, parse_dates=["timestamp"])
    if df.empty:
        return df
    df = df.set_index("timestamp")
    return df


def compute_vol_z(df_1m: pd.DataFrame) -> pd.DataFrame:
    """1m -> 1h close -> 1h log_ret -> 24h rolling std -> 30d z-score."""
    close_1h = df_1m["close"].resample("1h").last().dropna()
    log_ret_1h = np.log(close_1h / close_1h.shift(1))
    vol_1h_24h = log_ret_1h.rolling(window=VOL_ROLLING_HOURS, min_periods=18).std()
    v_mean = vol_1h_24h.rolling(window=ZSCORE_ROLLING_HOURS, min_periods=240).mean()
    v_std = vol_1h_24h.rolling(window=ZSCORE_ROLLING_HOURS, min_periods=240).std()
    z = (vol_1h_24h - v_mean) / v_std
    return pd.DataFrame({
        "close_1h": close_1h,
        "log_ret_1h": log_ret_1h,
        "vol_1h_24h": vol_1h_24h,
        "z_vol": z,
    })


def aggregate_to_4h(df_1m: pd.DataFrame) -> pd.DataFrame:
    """4h bar close + log returns for multiple hold horizons."""
    bar4h = df_1m["close"].resample("4h").last().dropna().to_frame("close")
    bar4h["log_ret_4h"] = np.log(bar4h["close"]).diff()
    return bar4h


def build_triggers_one_sided(sym_data: dict, hold_bars: int) -> pd.DataFrame:
    """Build LONG-only right-tail trigger rows.

    z_vol >= +2 (HIGH vol regime) -> LONG continuation, forward `hold_bars` 4h-bars
    Debounce DEBOUNCE_HOURS per-sym (8h = 2 bars).
    """
    rows = []
    for sym, d in sym_data.items():
        z = d["features"]["z_vol"]
        bar4h = d["bar4h"]

        # Resample z to 4h: last 1h within the 4h boundary
        z_4h = z.resample("4h").last().dropna()
        # Align to 4h bar index
        z_4h_aligned = z_4h.reindex(bar4h.index, method="ffill")
        bar4h = bar4h.copy()
        bar4h["z_vol"] = z_4h_aligned
        # Forward returns for the hold horizon
        bar4h["fwd_close"] = bar4h["close"].shift(-hold_bars)
        bar4h["fwd_log_ret"] = np.log(bar4h["fwd_close"] / bar4h["close"])

        last_ts = None
        for ts, row in bar4h.iterrows():
            z_val = row["z_vol"]
            # one-sided right-tail
            if pd.isna(z_val) or z_val < Z_THRESHOLD:
                continue
            if pd.isna(row["fwd_log_ret"]):
                continue
            if last_ts is not None and (ts - last_ts).total_seconds() < DEBOUNCE_HOURS * 3600:
                continue
            # LONG continuation: signed = +1 * fwd_ret
            signed_ret = float(row["fwd_log_ret"])  # LONG = +1
            rows.append({
                "ts": ts,
                "sym": sym,
                "z_vol": float(z_val),
                "fwd_log_ret": float(row["fwd_log_ret"]),
                "signed_ret": signed_ret,
                "qtr": str(ts.to_period("Q")),
                "year": ts.year,
            })
            last_ts = ts
    return pd.DataFrame(rows)


def candidate_pool_gross(sym_data: dict, hold_bars: int) -> np.ndarray:
    """All possible LONG-side 4h-bar entries (no trigger filter). Used for fee_aware_perm_test."""
    pool = []
    for sym, d in sym_data.items():
        bar4h = d["bar4h"].copy()
        bar4h["fwd_close"] = bar4h["close"].shift(-hold_bars)
        bar4h["fwd_log_ret"] = np.log(bar4h["fwd_close"] / bar4h["close"])
        pool.extend(bar4h["fwd_log_ret"].dropna().tolist())
    return np.array(pool)


def per_sym_concentration(trig_df: pd.DataFrame, fee: float, n_boot: int = 2000) -> dict:
    """Per-sym bootstrap CI lower & sign."""
    out = {}
    for sym, g in trig_df.groupby("sym"):
        net = g["signed_ret"].values - fee
        if len(net) < 5:
            out[sym] = {"n": int(len(net)), "ci_lower": None, "ci_pos": False, "gross_bp": None}
            continue
        ci = bootstrap_ci(net, n_boot=n_boot, block_size=1)
        out[sym] = {
            "n": int(len(net)),
            "gross_bp": float(g["signed_ret"].mean() * 10000.0),
            "net_bp": float(net.mean() * 10000.0),
            "ci_lower_bp": float(ci["ci_lower"] * 10000.0),
            "ci_upper_bp": float(ci["ci_upper"] * 10000.0),
            "ci_pos": bool(ci["ci_lower"] > 0),
            "prob_positive": float(ci["prob_positive"]),
        }
    return out


def per_quarter_diagnostics(trig_df: pd.DataFrame, fee: float) -> dict:
    """Per-quarter t-stat + edge + sharpe + sigex (LONG-only)."""
    out = {}
    for qtr, g in trig_df.groupby("qtr"):
        net = g["signed_ret"].values - fee
        n = len(net)
        if n < 2:
            out[qtr] = {"n": n, "gross_bp": None, "net_bp": None, "t": None,
                        "sharpe_per_trade": None, "edge_pct": None}
            continue
        gross = float(g["signed_ret"].mean()) * 10000.0
        net_m = float(net.mean()) * 10000.0
        net_sd = float(net.std(ddof=1))
        t = (net.mean() / net_sd * math.sqrt(n)) if net_sd > 0 else None
        sharpe = (net.mean() / net_sd) if net_sd > 0 else None
        edge_pct = float(net.mean()) * 100.0  # per-trade %
        out[qtr] = {
            "n": int(n), "gross_bp": gross, "net_bp": net_m, "t": t,
            "sharpe_per_trade": sharpe, "edge_pct": edge_pct,
        }
    return out


def era_stratify(trig_df: pd.DataFrame, fee: float) -> dict:
    """2024 / 2025 / 2026 era stratify."""
    out = {}
    for yr in [2024, 2025, 2026]:
        sub = trig_df[trig_df["year"] == yr]
        if len(sub) < 2:
            out[str(yr)] = {"n": int(len(sub)), "gross_bp": None,
                            "net_bp": None, "t": None, "sigex": None}
            continue
        net = sub["signed_ret"].values - fee
        gross = float(sub["signed_ret"].mean()) * 10000.0
        net_m = float(net.mean()) * 10000.0
        sd = float(net.std(ddof=1))
        t = (net.mean() / sd * math.sqrt(len(net))) if sd > 0 else None
        out[str(yr)] = {
            "n": int(len(sub)),
            "gross_bp": gross,
            "net_bp": net_m,
            "t": t,
        }
    return out


def main():
    start = time.time()
    log.info("paradigm %d R-1 start (KST %s)", PARADIGM_NUM,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("Lesson #55 candidate 1st explicit dogfood — one-sided right-tail LONG-only")

    engine = create_engine(DB_DSN)

    # --- Step 1: Substrate verification + feature compute ---
    log.info("--- Step 1: 1m OHLCV substrate per-sym + Lesson #30 exclude ---")
    sym_data = {}
    per_sym_days = {}
    universe_loaded = []
    universe_excluded = dict(LESSON_30_EXCLUDED)

    for sym in COHORT_FULL:
        if sym in LESSON_30_EXCLUDED:
            log.info("%s: SKIP (%s)", sym, LESSON_30_EXCLUDED[sym])
            continue
        try:
            df = load_ohlcv_1m(sym, engine)
            if df.empty or len(df) < 30 * 24 * 60 * 2:
                log.warning("%s: insufficient 1m data (n=%d) skip", sym, len(df))
                universe_excluded[sym] = f"insufficient_1m_data_n={len(df)}"
                continue
            days = (df.index.max() - df.index.min()).days
            per_sym_days[sym] = days
            feats = compute_vol_z(df)
            if feats["z_vol"].dropna().empty:
                log.warning("%s: empty z_vol skip", sym)
                universe_excluded[sym] = "empty_z_vol"
                continue
            bar4h = aggregate_to_4h(df)
            sym_data[sym] = {"features": feats, "bar4h": bar4h}
            universe_loaded.append(sym)
            log.info("%s: %d days, %d 1h vol, %d 4h bars, z range [%.2f, %.2f]",
                     sym, days, len(feats), len(bar4h),
                     float(feats["z_vol"].dropna().min()),
                     float(feats["z_vol"].dropna().max()))
        except Exception as e:
            log.error("%s load fail: %s", sym, e)
            universe_excluded[sym] = f"load_error_{e}"

    engine.dispose()

    if len(sym_data) < 5:
        log.error("insufficient universe (n=%d), abort", len(sym_data))
        sys.exit(1)

    full_window = max(per_sym_days.values()) if per_sym_days else 0
    log.info("Universe loaded: %d syms (full_window=%dd, excluded=%d)",
             len(sym_data), full_window, len(universe_excluded))

    # --- Step 2: Trigger build at multiple hold horizons ---
    log.info("--- Step 2: right-tail z >= +%.1f LONG-only trigger build ---", Z_THRESHOLD)
    results_per_hold = {}
    for hold_label, hold_bars in HOLD_BARS.items():
        trig_df = build_triggers_one_sided(sym_data, hold_bars)
        if trig_df.empty:
            log.error("hold=%s: zero triggers", hold_label)
            continue
        log.info("hold=%s: n_triggers=%d across %d syms",
                 hold_label, len(trig_df), trig_df["sym"].nunique())
        results_per_hold[hold_label] = {"trig_df": trig_df, "hold_bars": hold_bars}

    if PRIMARY_HOLD not in results_per_hold:
        log.error("primary hold %s missing, abort", PRIMARY_HOLD)
        sys.exit(1)

    # --- Step 3: Primary hold three-gate + concentration + temporal ---
    log.info("--- Step 3: PRIMARY hold=%s three-gate + concentration + temporal ---",
             PRIMARY_HOLD)
    primary = results_per_hold[PRIMARY_HOLD]
    trig_df = primary["trig_df"]
    hold_bars = primary["hold_bars"]

    # Gross/net + t
    obs_signed = trig_df["signed_ret"].values
    obs_net = obs_signed - FEE_RT
    n_obs = len(obs_net)
    gross_bp = float(obs_signed.mean()) * 10000.0
    net_bp = float(obs_net.mean()) * 10000.0
    net_sd = float(obs_net.std(ddof=1))
    obs_t = (obs_net.mean() / net_sd * math.sqrt(n_obs)) if net_sd > 0 else 0.0
    log.info("PRIMARY n=%d gross_bp=%.2f net_bp=%.2f obs_t=%.2f",
             n_obs, gross_bp, net_bp, obs_t)

    # fee_aware_perm_test
    pool_gross = candidate_pool_gross(sym_data, hold_bars)
    log.info("candidate pool size: %d (gross 4h returns across panel)", len(pool_gross))
    perm_res = fee_aware_perm_test(
        observed_net_returns=obs_net,
        candidate_pool_returns=pool_gross,
        fee_per_trade=FEE_RT,
        n_perms=1000,
    )
    log.info("fee_aware_perm: obs_t=%.2f null_mean_t=%.2f sigex=%.2f perm_p_above=%.4f",
             perm_res.get("obs_t", 0.0), perm_res.get("null_mean_t", 0.0),
             perm_res.get("signal_t_excess", 0.0),
             perm_res.get("perm_p_one_sided_above", 1.0))

    # bootstrap CI
    ci_res = bootstrap_ci(obs_net, n_boot=2000, block_size=1)
    log.info("bootstrap CI: mean=%.6f ci_lower=%.6f ci_upper=%.6f prob_pos=%.3f",
             ci_res["mean"], ci_res["ci_lower"], ci_res["ci_upper"],
             ci_res["prob_positive"])
    ci_lower_bp = ci_res["ci_lower"] * 10000.0
    ci_upper_bp = ci_res["ci_upper"] * 10000.0

    # Three-gate
    sigex = perm_res.get("signal_t_excess", float("nan"))
    perm_p = perm_res.get("perm_p_one_sided_above", float("nan"))
    gate_sigex = (sigex is not None and not math.isnan(sigex) and sigex >= 2.0)
    gate_ci = ci_res["ci_lower"] > 0
    gate_perm = (perm_p is not None and not math.isnan(perm_p) and perm_p <= 0.10)
    three_gate_pass = gate_sigex and gate_ci and gate_perm
    log.info("THREE-GATE: sigex>=2.0=%s (%.2f) AND ci_lower>0=%s (%.2fbp) AND perm_p<=0.10=%s (%.4f) -> %s",
             gate_sigex, sigex if sigex is not None else float("nan"),
             gate_ci, ci_lower_bp,
             gate_perm, perm_p if perm_p is not None else float("nan"),
             "PASS" if three_gate_pass else "FAIL")

    # Concentration Gate
    log.info("--- Concentration Gate: per-quarter t + per-symbol bootstrap ---")
    per_q = per_quarter_diagnostics(trig_df, FEE_RT)
    n_q_measurable = sum(1 for q in per_q.values() if q["n"] is not None and q["n"] >= 30)
    n_q_pos_t = sum(1 for q in per_q.values()
                    if q["t"] is not None and q["t"] > 0 and q["n"] >= 30)
    quarter_pos_t_ratio = (n_q_pos_t / n_q_measurable) if n_q_measurable > 0 else 0.0
    log.info("per-quarter: %d/%d measurable (n>=30), %d positive t",
             n_q_measurable, len(per_q), n_q_pos_t)
    for qtr in sorted(per_q.keys()):
        q = per_q[qtr]
        log.info("  %s: n=%d gross=%s t=%s sharpe=%s edge=%s%%", qtr, q["n"],
                 f"{q['gross_bp']:.2f}" if q["gross_bp"] is not None else "NA",
                 f"{q['t']:.2f}" if q["t"] is not None else "NA",
                 f"{q['sharpe_per_trade']:.3f}" if q["sharpe_per_trade"] is not None else "NA",
                 f"{q['edge_pct']:.3f}" if q["edge_pct"] is not None else "NA")

    per_sym_conc = per_sym_concentration(trig_df, FEE_RT, n_boot=2000)
    n_syms_measurable = sum(1 for s in per_sym_conc.values() if s["n"] >= 30)
    n_syms_ci_pos = sum(1 for s in per_sym_conc.values()
                       if s.get("ci_pos") and s["n"] >= 30)
    sym_ci_pos_ratio = (n_syms_ci_pos / n_syms_measurable) if n_syms_measurable > 0 else 0.0
    log.info("per-symbol bootstrap CI: %d/%d measurable, %d ci_pos",
             n_syms_measurable, len(per_sym_conc), n_syms_ci_pos)
    for sym in sorted(per_sym_conc.keys()):
        s = per_sym_conc[sym]
        if s["n"] >= 5:
            log.info("  %s: n=%d gross=%.2fbp ci_lower=%sbp ci_pos=%s",
                     sym, s["n"], s["gross_bp"] if s["gross_bp"] is not None else float("nan"),
                     f"{s['ci_lower_bp']:.2f}" if s.get("ci_lower_bp") is not None else "NA",
                     s.get("ci_pos"))

    # Concentration verdict
    conc_quarter_pass = quarter_pos_t_ratio >= 0.5
    conc_symbol_pass = sym_ci_pos_ratio >= 0.30 and n_syms_ci_pos >= 3
    conc_gate_pass = conc_quarter_pass and conc_symbol_pass
    log.info("Concentration Gate: quarter_pos_t_ratio=%.2f (>=0.5? %s), sym_ci_pos_ratio=%.2f / %d syms (>=0.30 AND >=3? %s) -> %s",
             quarter_pos_t_ratio, conc_quarter_pass,
             sym_ci_pos_ratio, n_syms_ci_pos, conc_symbol_pass,
             "PASS" if conc_gate_pass else "FAIL")

    # Temporal era stratify
    era = era_stratify(trig_df, FEE_RT)
    log.info("--- Era stratify ---")
    for yr in sorted(era.keys()):
        e = era[yr]
        log.info("  %s: n=%d gross_bp=%s net_bp=%s t=%s", yr, e["n"],
                 f"{e['gross_bp']:.2f}" if e["gross_bp"] is not None else "NA",
                 f"{e['net_bp']:.2f}" if e["net_bp"] is not None else "NA",
                 f"{e['t']:.2f}" if e["t"] is not None else "NA")

    # paradigm 136 direct comparison
    log.info("--- paradigm 136 baseline direct compare ---")
    p136_baseline = {
        "2024Q1": 267.28,
        "2024Q4": 33.83,
        "2025Q3": 68.92,
        "2026Q2": 1.34,
    }
    p136_compare = {}
    for qtr, p136_bp in p136_baseline.items():
        cur = per_q.get(qtr, {})
        p136_compare[qtr] = {
            "paradigm_136_baseline_gross_bp": p136_bp,
            "paradigm_202_current_gross_bp": cur.get("gross_bp"),
            "paradigm_202_current_n": cur.get("n", 0),
        }
        log.info("  %s: p136 baseline=%.2fbp | p202 current=%s (n=%s)",
                 qtr, p136_bp,
                 f"{cur.get('gross_bp'):.2f}" if cur.get("gross_bp") is not None else "NA",
                 cur.get("n", 0))

    # Decay verdict
    q_2024 = [v["gross_bp"] for k, v in per_q.items()
              if k.startswith("2024") and v["gross_bp"] is not None]
    q_2026 = [v["gross_bp"] for k, v in per_q.items()
              if k.startswith("2026") and v["gross_bp"] is not None]
    avg_2024 = float(np.mean(q_2024)) if q_2024 else None
    avg_2026 = float(np.mean(q_2026)) if q_2026 else None
    decay_ratio = (avg_2024 / avg_2026) if (avg_2024 and avg_2026 and avg_2026 != 0) else None
    log.info("Decay verdict: 2024 avg gross=%s | 2026 avg gross=%s | ratio=%s",
             f"{avg_2024:.2f}" if avg_2024 is not None else "NA",
             f"{avg_2026:.2f}" if avg_2026 is not None else "NA",
             f"{decay_ratio:.2f}x" if decay_ratio is not None else "NA")

    # 2026 era sigex check (CRITICAL Lesson #55 paradigm 136 decay verify)
    p202_2026 = era.get("2026", {})
    p202_2026_t = p202_2026.get("t")
    if p202_2026_t is not None and not math.isnan(p202_2026_t):
        if abs(p202_2026_t) >= 2.0 and p202_2026.get("net_bp", -1) > 0:
            decay_verdict = "REFUTED — 2026 era recent quarter PASS, paradigm 136 decay finding = variance regime mis-diagnosis"
        else:
            decay_verdict = "CONFIRMED — 2026 era recent quarter FAIL, paradigm 136 decay finding = universal alpha decay"
    else:
        decay_verdict = "INSUFFICIENT 2026 era sample"
    log.info("paradigm 136 decay verdict: %s", decay_verdict)

    # Life-changing 4-dim audit
    log.info("--- Life-changing 4-dim audit (LONG-only) ---")
    years_span = full_window / 365.25
    trades_per_year = (n_obs / years_span) if years_span > 0 else 0.0
    edge_pct = (obs_net.mean()) * 100.0  # per-trade %
    sharpe_per_trade = (obs_net.mean() / net_sd) if net_sd > 0 else 0.0
    sharpe_annualized = sharpe_per_trade * math.sqrt(trades_per_year) if trades_per_year > 0 else 0.0
    # Capital util: 4h hold, single-position-per-sym, max concurrent ~ n_syms
    # Approximation: avg active positions = trades/year * (4h hold / 8760h yr) * n_syms?
    # Simplified: 4h hold = 1/2190 yr, util_per_trade per-sym = 4h / 8760h = 0.000457
    # Total util_pct = trades_per_year * 0.000457 (assuming sequential)
    capital_util_pct = (trades_per_year * (4.0 / 8760.0)) * 100.0
    life_changing = {
        "trades_per_year": trades_per_year,
        "edge_pct_per_trade": edge_pct,
        "capital_util_pct": capital_util_pct,
        "sharpe_per_trade": sharpe_per_trade,
        "sharpe_annualized": sharpe_annualized,
        "gate_trades_yr_ge_12": bool(trades_per_year >= 12),
        "gate_edge_ge_2pct": bool(edge_pct >= 2.0),
        "gate_util_ge_30pct": bool(capital_util_pct >= 30.0),
        "gate_sharpe_ge_1_5": bool(sharpe_annualized >= 1.5),
    }
    life_changing["all_4_pass"] = (
        life_changing["gate_trades_yr_ge_12"] and
        life_changing["gate_edge_ge_2pct"] and
        life_changing["gate_util_ge_30pct"] and
        life_changing["gate_sharpe_ge_1_5"]
    )
    log.info("Life-changing: trades/yr=%.1f edge=%.3f%% util=%.2f%% sharpe_ann=%.2f -> all_4=%s",
             trades_per_year, edge_pct, capital_util_pct, sharpe_annualized,
             life_changing["all_4_pass"])

    # Hold sweep summary
    log.info("--- Hold sweep summary ---")
    hold_sweep = {}
    for hold_label, hh in results_per_hold.items():
        td = hh["trig_df"]
        if td.empty:
            continue
        net = td["signed_ret"].values - FEE_RT
        n = len(net)
        gbp = float(td["signed_ret"].mean()) * 10000.0
        nbp = float(net.mean()) * 10000.0
        sd = float(net.std(ddof=1))
        t = (net.mean() / sd * math.sqrt(n)) if sd > 0 else 0.0
        ci = bootstrap_ci(net, n_boot=1000, block_size=1)
        hold_sweep[hold_label] = {
            "n": int(n),
            "gross_bp": gbp,
            "net_bp": nbp,
            "obs_t": t,
            "ci_lower_bp": float(ci["ci_lower"] * 10000.0),
            "ci_pos": bool(ci["ci_lower"] > 0),
            "prob_positive": float(ci["prob_positive"]),
        }
        log.info("  hold=%s: n=%d gross=%.2fbp net=%.2fbp t=%.2f ci_lower=%.2fbp ci_pos=%s",
                 hold_label, n, gbp, nbp, t,
                 ci["ci_lower"] * 10000.0,
                 ci["ci_lower"] > 0)

    # Verdict ladder
    if not three_gate_pass:
        verdict = "BROAD_FALSIFIED_THREE_GATE_FAIL"
    elif not conc_gate_pass and not life_changing["all_4_pass"]:
        verdict = "CONCENTRATED_R1_PASS_NSLC_FAIL"
    elif not conc_gate_pass:
        verdict = "CONCENTRATED_R1_PASS"
    elif not life_changing["all_4_pass"]:
        verdict = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
    else:
        verdict = "PASS_R1_FULL"

    log.info("FINAL VERDICT: %s", verdict)

    # XRP cross-class verify
    xrp_check = per_sym_conc.get("XRPUSDT", {})

    elapsed = time.time() - start
    out = {
        "paradigm_name": PARADIGM_NAME,
        "paradigm_number": PARADIGM_NUM,
        "phase": "R-1",
        "verdict": verdict,
        "executed_at_kst": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "host": "hcp_local",
        "wall_clock_seconds": elapsed,
        "lesson_55_candidate_1st_explicit_dogfood": {
            "prescription_compliant": True,
            "one_sided_right_tail_only": True,
            "long_only_continuation": True,
            "snt_4quadrant_waived": True,
            "asymmetric_statistic_structure_honored": True,
        },
        "lesson_70_corollary_scope_verdict": "(b) direction_class_shift_NEW_paradigm_class — paradigm 184 precedent",
        "lesson_62_strict_distinct_vs_p136": "4/5 (statistic+frame+threshold+hold IDENTICAL, direction class SHIFT, universe EXPANDED)",
        "lesson_61_slug_grep_5th_post_confirmation_target": {
            "patterns_audited": [
                "right_tail", "one_sided", "long_only_directional",
                "right_tail_z", "asymmetric_z_one_sided", "one_sided_z",
                "right_tail_long_only",
            ],
            "hits": 0,
            "status": "5th post-confirmation success target — no prior slug DNA match",
        },
        "universe_cohort_proposed": COHORT_FULL,
        "universe_loaded": universe_loaded,
        "universe_excluded": universe_excluded,
        "params": {
            "vol_rolling_hours": VOL_ROLLING_HOURS,
            "zscore_rolling_hours": ZSCORE_ROLLING_HOURS,
            "z_threshold_right_tail": Z_THRESHOLD,
            "hold_bars": HOLD_BARS,
            "primary_hold": PRIMARY_HOLD,
            "debounce_hours": DEBOUNCE_HOURS,
            "fee_rt": FEE_RT,
        },
        "per_sym_days": per_sym_days,
        "n_observed": n_obs,
        "n_candidate_pool": int(len(pool_gross)),
        "gross_bp": gross_bp,
        "net_bp": net_bp,
        "obs_t": obs_t,
        "fee_aware_perm": {k: (float(v) if isinstance(v, (int, float, np.floating))
                              else v) for k, v in perm_res.items()},
        "bootstrap_ci": {
            "mean_bp": float(ci_res["mean"] * 10000.0),
            "ci_lower_bp": ci_lower_bp,
            "ci_upper_bp": ci_upper_bp,
            "prob_positive": float(ci_res["prob_positive"]),
            "n": int(ci_res["n"]),
        },
        "three_gate": {
            "sigex_pass": gate_sigex,
            "ci_lower_pos_pass": gate_ci,
            "perm_p_pass": gate_perm,
            "all_pass": three_gate_pass,
        },
        "concentration_gate": {
            "n_quarters_measurable": n_q_measurable,
            "n_quarters_total": len(per_q),
            "n_quarters_pos_t": n_q_pos_t,
            "quarter_pos_t_ratio": quarter_pos_t_ratio,
            "n_syms_measurable": n_syms_measurable,
            "n_syms_ci_pos": n_syms_ci_pos,
            "sym_ci_pos_ratio": sym_ci_pos_ratio,
            "all_pass": conc_gate_pass,
            "quarter_pass": conc_quarter_pass,
            "symbol_pass": conc_symbol_pass,
        },
        "per_quarter_diagnostics": per_q,
        "per_sym_concentration": per_sym_conc,
        "era_stratify": era,
        "paradigm_136_baseline_compare": p136_compare,
        "decay_verdict": {
            "avg_2024_gross_bp": avg_2024,
            "avg_2026_gross_bp": avg_2026,
            "ratio_2024_over_2026": decay_ratio,
            "paradigm_136_decay_status": decay_verdict,
        },
        "life_changing_4dim_audit": life_changing,
        "hold_sweep": hold_sweep,
        "xrp_cross_class_verify": xrp_check,
    }

    out_path = OUT_DIR / "r1_metrics.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    log.info("R-1 saved to %s (wall=%.1fs)", out_path, elapsed)
    log.info("FINAL: %s", verdict)


if __name__ == "__main__":
    main()
