"""paradigm 137 R-1 PoC — alt_intraday_realized_range_close_to_close_efficiency_ratio_z_directional_4h.

Yang-Zhang / Garman-Klass (2000) range vs close-to-close efficiency ratio.

R-0 advisory (from r0_prescreen.json):
  - Lesson #21 sub-finding: PASS (1/12 syms corr>0.95, log_ER std ≈0.28 sufficient)
  - Lesson #40: PASS (z range [-3.77, +7.36])
  - Lesson #55: SYMMETRIC (asym ratio 2.81 < 5.0; log-transform restored neg side)
  - Lesson #11 density: PASS (chop_fade 10/10q, drift_continue 8/10q ≥30)
  - Lesson #46 sub-amendment per-quarter R-0 STRONG WARNING:
      A_focus chop_fade per-q signs [-,+,+,+] (1 flip, Q1 outlier -79bp)
      B_focus drift_continue per-q signs [-,-,-,-] (0 flips, ALL NEGATIVE: -69,-41,-31,-27)
  - Stratified R-0 4-quadrant gross:
      A_focus chop_fade  = -2.28bp  (~0 noise)
      A_mirror           = +2.28bp  (~0 noise)
      B_focus drift_continue = -37.62bp (consistent negative drift)
      B_mirror drift_fade    = +37.62bp (mirror likely PASS)
  - HYPOTHESIS REFRAMING:
      Original: chop -> fade / drift -> continue
      Empirical advisory: drift regime (z<-2) -> CONTINUE FAILS, FADE may pass
      i.e., low-vol-range regime sustains REVERSAL not continuation
      Lesson #53 candidate detection enabled at R-1

4-quadrant SNT (Lesson #19 mandatory):
  A_focus  = z_logER>+2 (chop) × OPPOSITE trigger sign (fade move)   [chop_fade]
  A_mirror = z_logER>+2 (chop) × SAME trigger sign     (continue)    [chop_continue]
  B_focus  = z_logER<-2 (drift) × SAME trigger sign    (continue)    [drift_continue]
  B_mirror = z_logER<-2 (drift) × OPPOSITE trigger sign (fade)       [drift_fade]

R-1 three-gate per quadrant:
  signal_t_excess >= 2.0 AND ci_lower > 0 AND perm_p_one_sided <= 0.10

Concentration Gate (Lesson #16 STRICT):
  quarter_pos_t_ratio >= 0.5 AND symbol_ci_pos_ratio >= 0.30 AND n_symbols_ci_pos >= 3

Family-distinct verification (Lesson #44 amendment 20th dogfood):
  paradigm 137 = ratio CLASSIFIER (regime), NOT raw magnitude
    -> distinct from paradigm 129 raw Parkinson (vol magnitude estimator)
    -> distinct from paradigm 135 cross-domain VRP (intra-OHLC within-domain)
    -> distinct from paradigm 136 1st-order intraday std (magnitude, log_ER is ratio)

Range estimator family 2nd dogfood:
  If 137 BROAD_FALSIFIED OR CONCENTRATED_R1_PASS AND mirror not PASS_R1_FULL
    -> family retire candidate elevation (2 dogfoods)
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

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.research._perm_utils import (  # noqa: E402
    fee_aware_perm_test,
    bootstrap_ci,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("p137_r1")

PARADIGM_NAME = "alt_intraday_realized_range_close_to_close_efficiency_ratio_z_directional_4h"
PARADIGM_NUM = 137
OUT_DIR = Path(f"/home/hcpark/antigravity/backend/runs/research_track/{PARADIGM_NAME}")
OUT_DIR.mkdir(parents=True, exist_ok=True)

COHORT = [
    "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT",
    "NEARUSDT", "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

ROLLING_SUM_HOURS = 24
ZSCORE_ROLLING_HOURS = 30 * 24
Z_THRESHOLD = 2.0
FORWARD_HOLD_4H_BARS = 1
DEBOUNCE_HOURS = 8
FEE_PER_TRADE = 0.0016
FEE_BP = FEE_PER_TRADE * 10000.0
N_PERMS = 1000
N_BOOT = 2000
PARKINSON_CONST = 1.0 / (4.0 * math.log(2.0))
DB_DSN = "postgresql://antigravity_user:antigravity_password@localhost:5432/antigravity_db"


def load_ohlcv_1m(sym: str, engine) -> pd.DataFrame:
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
    ohlc_1h = pd.DataFrame({
        "open":  df_1m["open"].resample("1h").first(),
        "high":  df_1m["high"].resample("1h").max(),
        "low":   df_1m["low"].resample("1h").min(),
        "close": df_1m["close"].resample("1h").last(),
    }).dropna()
    return ohlc_1h


def compute_log_ER_z(ohlc_1h: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Compute log_ER (Yang-Zhang efficiency ratio) and per-symbol 30d z-score."""
    h = ohlc_1h["high"].astype(float)
    l = ohlc_1h["low"].astype(float)
    c = ohlc_1h["close"].astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        P = PARKINSON_CONST * (np.log(h / l) ** 2)
    P = P.replace([np.inf, -np.inf], np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        C = (np.log(c / c.shift(1))) ** 2
    C = C.replace([np.inf, -np.inf], np.nan)
    sum_P = P.rolling(window=ROLLING_SUM_HOURS, min_periods=18).sum()
    sum_C = C.rolling(window=ROLLING_SUM_HOURS, min_periods=18).sum()
    with np.errstate(divide="ignore", invalid="ignore"):
        ER = sum_P / sum_C
        log_ER = np.log(ER)
    log_ER = log_ER.replace([np.inf, -np.inf], np.nan)
    m = log_ER.rolling(window=ZSCORE_ROLLING_HOURS, min_periods=240).mean()
    s = log_ER.rolling(window=ZSCORE_ROLLING_HOURS, min_periods=240).std()
    z = (log_ER - m) / s
    return log_ER, z


def aggregate_to_4h(df_1m: pd.DataFrame) -> pd.DataFrame:
    bar4h = df_1m["close"].resample("4h").last().dropna().to_frame("close")
    bar4h["log_ret_4h"] = np.log(bar4h["close"]).diff()
    return bar4h


def build_panel():
    engine = create_engine(DB_DSN)
    panels = {}
    for sym in COHORT:
        df = load_ohlcv_1m(sym, engine)
        if df.empty or len(df) < 30 * 24 * 60 * 2:
            log.warning("%s skip insufficient data", sym)
            continue
        ohlc_1h = aggregate_to_1h_ohlc(df)
        if len(ohlc_1h) < ZSCORE_ROLLING_HOURS + ROLLING_SUM_HOURS:
            log.warning("%s skip insufficient 1h OHLC", sym)
            continue
        log_ER, z = compute_log_ER_z(ohlc_1h)
        bar4h = aggregate_to_4h(df)
        # take z at 4h boundary (last 1h value within each 4h interval)
        z_4h = z.resample("4h").last().dropna()
        bar4h = bar4h.copy()
        bar4h["z_logER"] = z_4h.reindex(bar4h.index, method="ffill")
        bar4h["fwd_log_ret_4h"] = bar4h["log_ret_4h"].shift(-FORWARD_HOLD_4H_BARS)
        bar4h["cond_chop"] = bar4h["z_logER"] > Z_THRESHOLD     # A side
        bar4h["cond_drift"] = bar4h["z_logER"] < -Z_THRESHOLD   # B side
        bar4h["sym"] = sym
        panels[sym] = bar4h
        log.info("%s panel built: bars=%d z_range=[%.2f, %.2f]",
                 sym, len(bar4h), float(z.min()), float(z.max()))
    engine.dispose()
    return panels


def make_triggers(panel: dict) -> pd.DataFrame:
    """Two trigger groups: A (chop, z>+2) and B (drift, z<-2)."""
    rows = []
    for sym, df in panel.items():
        last_ts = None
        for ts, row in df.iterrows():
            cond_chop = bool(row["cond_chop"]) if not pd.isna(row["cond_chop"]) else False
            cond_drift = bool(row["cond_drift"]) if not pd.isna(row["cond_drift"]) else False
            if not (cond_chop or cond_drift):
                continue
            if pd.isna(row["log_ret_4h"]) or pd.isna(row["fwd_log_ret_4h"]):
                continue
            if last_ts is not None and (ts - last_ts).total_seconds() < DEBOUNCE_HOURS * 3600:
                continue
            trig_sign = int(np.sign(row["log_ret_4h"]))
            if trig_sign == 0:
                continue
            # group: A = chop (z>+2), B = drift (z<-2)
            group = "A_chop" if cond_chop else "B_drift"
            rows.append({
                "ts": ts,
                "sym": sym,
                "z_logER": float(row["z_logER"]),
                "trig_sign": trig_sign,
                "group": group,
                "log_ret_4h": float(row["log_ret_4h"]),
                "fwd_log_ret_4h": float(row["fwd_log_ret_4h"]),
                "qtr": str(ts.to_period("Q")),
            })
            last_ts = ts
    return pd.DataFrame(rows)


def build_candidate_pool(panel: dict) -> np.ndarray:
    pool = []
    for sym, df in panel.items():
        valid = df["fwd_log_ret_4h"].dropna()
        pool.extend(valid.tolist())
    return np.array(pool)


def evaluate_quadrant(trades_net: np.ndarray, pool_gross: np.ndarray,
                      direction_sign_in_pool: int) -> dict:
    """direction_sign_in_pool: +1 if quadrant LONGs (matches pool sign),
                              -1 if quadrant SHORTs (negate pool)."""
    if len(trades_net) < 30:
        return {"n": int(len(trades_net)), "error": "n<30"}

    pool_directed = pool_gross.copy() if direction_sign_in_pool > 0 else -pool_gross.copy()

    perm = fee_aware_perm_test(
        observed_net_returns=trades_net,
        candidate_pool_returns=pool_directed,
        fee_per_trade=FEE_PER_TRADE,
        n_perms=N_PERMS,
    )
    boot = bootstrap_ci(trades_net, n_boot=N_BOOT, block_size=1)

    obs_t = perm["obs_t"]
    signal_t_excess = perm["signal_t_excess"]
    perm_p = perm["perm_p_one_sided_above"]
    ci_lower = boot["ci_lower"]
    ci_lower_bp = ci_lower * 10000.0 if not pd.isna(ci_lower) else float("nan")
    mean_bp = float(np.mean(trades_net) * 10000.0)
    gross_bp = mean_bp + FEE_BP

    gate_excess = bool(signal_t_excess >= 2.0 if not pd.isna(signal_t_excess) else False)
    gate_ci = bool(ci_lower > 0 if not pd.isna(ci_lower) else False)
    gate_perm = bool(perm_p <= 0.10 if not pd.isna(perm_p) else False)
    three_gate_pass = bool(gate_excess and gate_ci and gate_perm)

    return {
        "n": int(len(trades_net)),
        "gross_bp": gross_bp,
        "net_bp": mean_bp,
        "obs_t": obs_t,
        "null_mean_t": perm["null_mean_t"],
        "null_std_t": perm["null_std_t"],
        "signal_t_excess": signal_t_excess,
        "perm_p_one_sided_above": perm_p,
        "perm_p_two_sided": perm["perm_p_two_sided"],
        "ci_lower_bp": ci_lower_bp,
        "ci_upper_bp": (boot["ci_upper"] * 10000.0
                        if not pd.isna(boot["ci_upper"]) else float("nan")),
        "prob_positive": boot["prob_positive"],
        "gate_excess": gate_excess,
        "gate_ci": gate_ci,
        "gate_perm": gate_perm,
        "three_gate_pass": three_gate_pass,
    }


def concentration_diagnostics(trig_df: pd.DataFrame, group_filter: str,
                              direction_sign_in_trigger: int, name: str) -> dict:
    """direction_sign_in_trigger: +1 = LONG (use trig_sign as direction),
                                  -1 = OPPOSITE (negate trig_sign as direction)."""
    subset = trig_df[trig_df["group"] == group_filter].copy()
    if subset.empty:
        return {"name": name, "n": 0, "error": "empty"}
    # for fade quadrant: direction = -trig_sign; for continue: direction = +trig_sign
    subset["dir"] = subset["trig_sign"] * direction_sign_in_trigger
    subset["net_bp"] = subset["fwd_log_ret_4h"] * subset["dir"] * 10000.0 - FEE_BP

    per_qtr_t = {}
    for q, grp in subset.groupby("qtr"):
        if len(grp) >= 10:
            arr = grp["net_bp"].values
            sd = arr.std(ddof=1)
            t_q = float(arr.mean() / (sd / math.sqrt(len(arr)))) if sd > 0 else 0.0
            per_qtr_t[q] = {"n": int(len(grp)), "t": t_q, "mean_bp": float(arr.mean())}
    n_measurable_q = len(per_qtr_t)
    n_pos_q = sum(1 for v in per_qtr_t.values() if v["t"] > 0)
    quarter_pos_t_ratio = (n_pos_q / n_measurable_q) if n_measurable_q else 0.0

    per_sym_ci = {}
    for s, grp in subset.groupby("sym"):
        if len(grp) >= 20:
            net = grp["net_bp"].values / 10000.0
            boot = bootstrap_ci(net, n_boot=1000, block_size=1)
            per_sym_ci[s] = {
                "n": int(len(grp)),
                "ci_lower_bp": (float(boot["ci_lower"] * 10000.0)
                                if not pd.isna(boot["ci_lower"]) else None),
                "ci_pos": (bool(boot["ci_lower"] > 0)
                           if not pd.isna(boot["ci_lower"]) else False),
                "mean_bp": float(grp["net_bp"].mean()),
            }
    n_measurable_sym = len(per_sym_ci)
    n_ci_pos = sum(1 for v in per_sym_ci.values() if v["ci_pos"])
    symbol_ci_pos_ratio = (n_ci_pos / n_measurable_sym) if n_measurable_sym else 0.0

    gate_quarter = bool(quarter_pos_t_ratio >= 0.5)
    gate_symbol_ratio = bool(symbol_ci_pos_ratio >= 0.30)
    gate_symbol_count = bool(n_ci_pos >= 3)
    concentration_gate_pass = bool(gate_quarter and gate_symbol_ratio and gate_symbol_count)

    return {
        "name": name,
        "n_total": int(len(subset)),
        "per_quarter_t": per_qtr_t,
        "n_measurable_q": int(n_measurable_q),
        "n_pos_q": int(n_pos_q),
        "quarter_pos_t_ratio": quarter_pos_t_ratio,
        "per_symbol_ci": per_sym_ci,
        "n_measurable_sym": int(n_measurable_sym),
        "n_ci_pos": int(n_ci_pos),
        "symbol_ci_pos_ratio": symbol_ci_pos_ratio,
        "gate_quarter": gate_quarter,
        "gate_symbol_ratio": gate_symbol_ratio,
        "gate_symbol_count": gate_symbol_count,
        "concentration_gate_pass": concentration_gate_pass,
    }


def main():
    log.info("paradigm %d R-1 start (KST %s)", PARADIGM_NUM,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    panel = build_panel()
    log.info("panel built: %d symbols", len(panel))

    trig_df = make_triggers(panel)
    n_total = len(trig_df)
    n_a = int((trig_df["group"] == "A_chop").sum())
    n_b = int((trig_df["group"] == "B_drift").sum())
    log.info("triggers total=%d (A_chop=%d, B_drift=%d)", n_total, n_a, n_b)

    if n_total < 100:
        log.error("insufficient triggers (n=%d < 100) — graveyard", n_total)
        sys.exit(2)

    pool_gross = build_candidate_pool(panel)
    log.info("candidate pool: n=%d (unconditional fwd_log_ret_4h)", len(pool_gross))

    a_trig = trig_df[trig_df["group"] == "A_chop"].copy()
    b_trig = trig_df[trig_df["group"] == "B_drift"].copy()

    # A_focus = chop_fade (z>+2, direction = -trig_sign): signed_fwd = fwd * (-trig_sign)
    # A_mirror = chop_continue (z>+2, direction = +trig_sign): signed_fwd = fwd * (+trig_sign)
    # B_focus = drift_continue (z<-2, direction = +trig_sign): signed_fwd = fwd * (+trig_sign)
    # B_mirror = drift_fade (z<-2, direction = -trig_sign): signed_fwd = fwd * (-trig_sign)
    a_focus_net = (a_trig["fwd_log_ret_4h"].values * (-1.0) * a_trig["trig_sign"].values) - FEE_PER_TRADE
    a_mirror_net = (a_trig["fwd_log_ret_4h"].values * (+1.0) * a_trig["trig_sign"].values) - FEE_PER_TRADE
    b_focus_net = (b_trig["fwd_log_ret_4h"].values * (+1.0) * b_trig["trig_sign"].values) - FEE_PER_TRADE
    b_mirror_net = (b_trig["fwd_log_ret_4h"].values * (-1.0) * b_trig["trig_sign"].values) - FEE_PER_TRADE

    log.info("--- Evaluating 4 quadrants ---")
    # direction_sign_in_pool: we test if quadrant's sign-aligned returns exceed pool
    # For a "fade" quadrant, observed = -trig_sign × fwd; the pool we test against
    # should be the unconditional fwd_4h sign-randomized (sign of trig from pool, then negate)
    # Simplification (as in p133): pass pool as-is for LONG side, negate for SHORT side.
    # But each quadrant here mixes pos/neg trig_signs; the perm null is invariant
    # to direction since it just samples from pool. We use pool_gross direct.
    quadrants = {
        "A_focus_chop_fade":         (a_focus_net,  +1),
        "A_mirror_chop_continue":    (a_mirror_net, +1),
        "B_focus_drift_continue":    (b_focus_net,  +1),
        "B_mirror_drift_fade":       (b_mirror_net, +1),
    }
    quad_results = {}
    for qname, (trades, pool_sign) in quadrants.items():
        res = evaluate_quadrant(trades, pool_gross, pool_sign)
        quad_results[qname] = res
        if "error" in res:
            log.warning("  %s: %s", qname, res)
        else:
            log.info(
                "  %s: n=%d gross=%.2fbp net=%.2fbp obs_t=%.2f null_t=%.2f "
                "sigex=%.2f ci_lower=%.2fbp perm_p=%.3f 3gate=%s "
                "(excess=%s ci=%s perm=%s)",
                qname, res["n"], res["gross_bp"], res["net_bp"],
                res["obs_t"], res["null_mean_t"], res["signal_t_excess"],
                res["ci_lower_bp"], res["perm_p_one_sided_above"],
                res["three_gate_pass"], res["gate_excess"], res["gate_ci"],
                res["gate_perm"])

    log.info("--- Concentration diagnostics (Lesson #16 STRICT) ---")
    conc_specs = [
        ("A_focus_chop_fade",       "A_chop", -1),
        ("A_mirror_chop_continue",  "A_chop", +1),
        ("B_focus_drift_continue",  "B_drift", +1),
        ("B_mirror_drift_fade",     "B_drift", -1),
    ]
    conc_results = {}
    for name, gfilter, dsign in conc_specs:
        c = concentration_diagnostics(trig_df, gfilter, dsign, name)
        conc_results[name] = c
        if "error" in c:
            log.warning("  conc %s: %s", name, c)
        else:
            log.info(
                "  conc %s: n=%d q_pos_t=%d/%d ratio=%.2f sym_ci_pos=%d/%d ratio=%.2f "
                "concentration_gate=%s",
                name, c["n_total"], c["n_pos_q"], c["n_measurable_q"],
                c["quarter_pos_t_ratio"], c["n_ci_pos"], c["n_measurable_sym"],
                c["symbol_ci_pos_ratio"], c["concentration_gate_pass"])

    pass_quadrants = [q for q, r in quad_results.items()
                      if r.get("three_gate_pass", False)]
    log.info("=== R-1 PASSING quadrants: %s ===", pass_quadrants if pass_quadrants else "NONE")

    # Lesson #52 a/b detection: both LONG-equivalent quadrants positive while concentration low
    # Here A_focus (chop_fade) + B_mirror (drift_fade) are both "fade" semantic
    a_focus_net_bp = quad_results.get("A_focus_chop_fade", {}).get("net_bp", 0)
    b_mirror_net_bp = quad_results.get("B_mirror_drift_fade", {}).get("net_bp", 0)
    a_focus_conc_n = conc_results.get("A_focus_chop_fade", {}).get("n_ci_pos", 0)
    b_mirror_conc_n = conc_results.get("B_mirror_drift_fade", {}).get("n_ci_pos", 0)
    lesson_52_pattern = bool(
        a_focus_net_bp > 0 and b_mirror_net_bp > 0
        and a_focus_conc_n == 0 and b_mirror_conc_n == 0
    )

    # Lesson #53 candidate: focus FAIL + mirror PASS = hypothesis dir inverted
    a_focus_gross = quad_results.get("A_focus_chop_fade", {}).get("gross_bp", 0)
    a_mirror_gross = quad_results.get("A_mirror_chop_continue", {}).get("gross_bp", 0)
    b_focus_gross = quad_results.get("B_focus_drift_continue", {}).get("gross_bp", 0)
    b_mirror_gross = quad_results.get("B_mirror_drift_fade", {}).get("gross_bp", 0)
    lesson_53_a_inverted = (a_focus_gross < 0 and a_mirror_gross > 0
                            and (a_mirror_gross - a_focus_gross > 20))
    lesson_53_b_inverted = (b_focus_gross < 0 and b_mirror_gross > 0
                            and (b_mirror_gross - b_focus_gross > 20))

    def is_neg(q):
        r = quad_results.get(q, {})
        return r.get("net_bp", 0) < 0 and not r.get("three_gate_pass", False)

    a_focus_neg = is_neg("A_focus_chop_fade")
    a_mirror_neg = is_neg("A_mirror_chop_continue")
    b_focus_neg = is_neg("B_focus_drift_continue")
    b_mirror_neg = is_neg("B_mirror_drift_fade")

    if not pass_quadrants:
        if a_focus_neg and a_mirror_neg and b_focus_neg and b_mirror_neg:
            verdict = "BROAD_FALSIFIED_BOTH_FOCUS_NEGATIVE"
            sub_class = ("A_broad_uniform_negative_no_axis_synthesis "
                         "(Lesson #39 sub-class A — ratio has no directional info)")
        elif a_focus_neg and b_focus_neg:
            if lesson_53_a_inverted and lesson_53_b_inverted:
                verdict = "BROAD_FALSIFIED_MIRROR_DIRECTION_INVERTED"
                sub_class = ("Lesson #39 sub-class B / Lesson #53 candidate — "
                             "both focus negative, both mirrors positive (inverted but sub-fee)")
            elif lesson_53_b_inverted:
                verdict = "BROAD_FALSIFIED_B_MIRROR_INVERTED_PARTIAL"
                sub_class = ("Lesson #53 candidate — B drift_continue FAIL, "
                             "B drift_fade mirror INVERTED candidate; A side ~noise")
            else:
                verdict = "BROAD_FALSIFIED_FOCUS_DIRECTION_FAIL"
                sub_class = "focus quadrants both negative (mechanism direction wrong or noise)"
        elif a_focus_neg and a_mirror_neg:
            verdict = "BROAD_FALSIFIED_A_FOCUS_NEGATIVE"
            sub_class = "A pair both negative"
        elif b_focus_neg and b_mirror_neg:
            verdict = "BROAD_FALSIFIED_B_FOCUS_NEGATIVE"
            sub_class = "B pair both negative"
        else:
            verdict = "BROAD_FALSIFIED_MIXED"
            sub_class = "mixed quadrant negativity"
    else:
        passing_with_conc = []
        for q in pass_quadrants:
            cres = conc_results.get(q, {})
            if cres.get("concentration_gate_pass", False):
                passing_with_conc.append(q)
        if passing_with_conc:
            verdict = "PASS_R1_FULL"
            sub_class = f"three-gate PASS + Concentration Gate PASS: {passing_with_conc}"
        else:
            verdict = "CONCENTRATED_R1_PASS"
            sub_class = f"three-gate PASS but Concentration FAIL: {pass_quadrants}"

    log.info("=== VERDICT: %s ===", verdict)
    log.info("=== SUB-CLASS: %s ===", sub_class)
    log.info("Lesson #52 a/b pattern (both fade quadrants pos + 0 syms ci_pos): %s",
             lesson_52_pattern)
    log.info("Lesson #53 A direction inverted (focus<0, mirror>0, gap>20bp): %s",
             lesson_53_a_inverted)
    log.info("Lesson #53 B direction inverted (focus<0, mirror>0, gap>20bp): %s",
             lesson_53_b_inverted)

    # Lesson #46 sub-amendment 12th dogfood: post-R-1 per-quarter sign-flip across full data
    log.info("--- Lesson #46 sub-amendment 12th dogfood post-R-1 per-quarter ---")
    full_signs = {}
    for qname, group_filter, dsign in [
        ("A_focus_chop_fade",      "A_chop",  -1),
        ("B_focus_drift_continue", "B_drift", +1),
    ]:
        per_q_full = {}
        sub = trig_df[trig_df["group"] == group_filter].copy()
        sub["net_bp"] = sub["fwd_log_ret_4h"] * sub["trig_sign"] * dsign * 10000.0 - FEE_BP
        for q, grp in sub.groupby("qtr"):
            if len(grp) >= 30:
                per_q_full[q] = {"n": int(len(grp)), "mean_bp": float(grp["net_bp"].mean())}
        signs = [1 if v["mean_bp"] > 0 else -1 for v in per_q_full.values()]
        flips = sum(1 for i in range(1, len(signs)) if signs[i] != signs[i - 1])
        full_signs[qname] = {
            "per_qtr_mean_bp": per_q_full,
            "signs": signs,
            "n_flips": flips,
            "n_pos_q": sum(1 for s in signs if s > 0),
            "n_neg_q": sum(1 for s in signs if s < 0),
        }
        log.info("  %s: signs=%s flips=%d (pos=%d/neg=%d)", qname, signs, flips,
                 full_signs[qname]["n_pos_q"], full_signs[qname]["n_neg_q"])

    out = {
        "paradigm_name": PARADIGM_NAME,
        "paradigm_number": PARADIGM_NUM,
        "phase": "R-1",
        "executed_at_kst": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "host": "hcp_local",
        "verdict": verdict,
        "sub_class": sub_class,
        "passing_quadrants": pass_quadrants,
        "params": {
            "rolling_sum_hours": ROLLING_SUM_HOURS,
            "zscore_rolling_hours": ZSCORE_ROLLING_HOURS,
            "z_threshold": Z_THRESHOLD,
            "forward_hold_4h_bars": FORWARD_HOLD_4H_BARS,
            "debounce_hours": DEBOUNCE_HOURS,
            "fee_per_trade": FEE_PER_TRADE,
            "fee_bp": FEE_BP,
            "n_perms": N_PERMS,
            "n_boot": N_BOOT,
            "parkinson_const": PARKINSON_CONST,
        },
        "universe_loaded": list(panel.keys()),
        "n_triggers_total": int(n_total),
        "n_triggers_A_chop": n_a,
        "n_triggers_B_drift": n_b,
        "candidate_pool_n": int(len(pool_gross)),
        "quadrant_results": quad_results,
        "concentration_diagnostics": conc_results,
        "lesson_52_a_b_pattern_fade": lesson_52_pattern,
        "lesson_53_a_direction_inverted": lesson_53_a_inverted,
        "lesson_53_b_direction_inverted": lesson_53_b_inverted,
        "lesson_46_sub_amendment_post_r1_per_qtr_full": full_signs,
        "range_estimator_family_dogfood_count": 2,
    }

    out_path = OUT_DIR / "r1__metrics.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    log.info("R-1 saved to %s", out_path)


if __name__ == "__main__":
    main()
