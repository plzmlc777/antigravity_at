"""paradigm 129 R-1 PoC — alt_parkinson_range_vol_expansion_percentile_directional_4h.

4-quadrant SNT (Lesson #19 mandatory):
  A_focus  = trigger ∩ direction>0 × LONG    (range expand UP -> momentum continuation)
  A_mirror = trigger ∩ direction>0 × SHORT   (range expand UP -> fade)
  B_focus  = trigger ∩ direction<0 × SHORT   (range expand DOWN -> momentum continuation)
  B_mirror = trigger ∩ direction<0 × LONG    (range expand DOWN -> reversion)

R-1 three-gate per quadrant:
  signal_t_excess >= 2.0 AND ci_lower > 0 AND perm_p_one_sided <= 0.10

Concentration Gate (Lesson #16):
  quarter_pos_t_ratio >= 0.5 AND symbol_ci_pos_ratio >= 0.30 AND n_symbols_ci_pos >= 3

R-0 advisory: A_focus 3 sign flips + B_focus alternating = R-0 already shows
unstable quarter-by-quarter pattern; R-1 will confirm full-pool verdict.
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
log = logging.getLogger("p129_r1")

PARADIGM_NAME = "alt_parkinson_range_vol_expansion_percentile_directional_4h"
PARADIGM_NUM = 129
OUT_DIR = Path(f"/home/hcpark/antigravity/backend/runs/research_track/{PARADIGM_NAME}")
OUT_DIR.mkdir(parents=True, exist_ok=True)

COHORT = [
    "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT",
    "NEARUSDT", "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

PARK_ROLLING_BARS_4H = 180
PARK_PERCENTILE = 90.0
FORWARD_HOLD_4H_BARS = 1
DEBOUNCE_HOURS = 8
FEE_PER_TRADE = 0.0016  # 16bp round-trip = 0.0016 (matches paradigm 126/127/128)
FEE_BP = FEE_PER_TRADE * 10000.0
N_PERMS = 1000
N_BOOT = 2000
DB_DSN = "postgresql://antigravity_user:antigravity_password@localhost:5432/antigravity_db"


def load_4h(sym: str, engine) -> pd.DataFrame:
    q = text(
        "SELECT timestamp, high, low, close FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
    )
    df = pd.read_sql(q, engine, params={"s": sym}, parse_dates=["timestamp"])
    if df.empty:
        return df
    df = df.set_index("timestamp")
    bar4h = df.resample("4h").agg({"high": "max", "low": "min", "close": "last"}).dropna()
    return bar4h


def build_panel():
    engine = create_engine(DB_DSN)
    panels = {}
    for sym in COHORT:
        df = load_4h(sym, engine)
        if df.empty or len(df) < PARK_ROLLING_BARS_4H * 2:
            log.warning("%s skip insufficient data", sym)
            continue
        df["park"] = (1.0 / (4.0 * np.log(2.0))) * (np.log(df["high"] / df["low"])) ** 2
        df["log_ret_4h"] = np.log(df["close"]).diff()
        df["park_p90_30d"] = (
            df["park"].rolling(window=PARK_ROLLING_BARS_4H,
                                min_periods=PARK_ROLLING_BARS_4H // 2)
            .quantile(PARK_PERCENTILE / 100)
        )
        df["fwd_log_ret_4h"] = df["log_ret_4h"].shift(-FORWARD_HOLD_4H_BARS)
        df["cond"] = df["park"] >= df["park_p90_30d"]
        df["sym"] = sym
        panels[sym] = df
    return panels


def make_triggers(panel: dict) -> pd.DataFrame:
    rows = []
    for sym, df in panel.items():
        last_ts = None
        for ts, row in df.iterrows():
            if (pd.isna(row["cond"]) or not row["cond"]
                    or pd.isna(row["log_ret_4h"])
                    or pd.isna(row["fwd_log_ret_4h"])):
                continue
            if last_ts is not None and (ts - last_ts).total_seconds() < DEBOUNCE_HOURS * 3600:
                continue
            d = int(np.sign(row["log_ret_4h"]))
            if d == 0:
                continue
            rows.append({
                "ts": ts,
                "sym": sym,
                "park": float(row["park"]),
                "direction": d,
                "log_ret_4h": float(row["log_ret_4h"]),
                "fwd_log_ret_4h": float(row["fwd_log_ret_4h"]),
                "qtr": str(ts.to_period("Q")),
            })
            last_ts = ts
    return pd.DataFrame(rows)


def build_candidate_pool(panel: dict) -> np.ndarray:
    """Unconditional fwd_ret pool for fee_aware_perm_test (Lesson #49 5+1 dogfood).

    All valid (cond not required) fwd_log_ret_4h across full panel — both
    directional flavors (will be applied per-quadrant via sign multiplication
    in the quadrant evaluator).
    """
    pool = []
    for sym, df in panel.items():
        valid = df["fwd_log_ret_4h"].dropna()
        pool.extend(valid.tolist())
    return np.array(pool)


def evaluate_quadrant(trades_net: np.ndarray, pool_gross: np.ndarray,
                     direction_label: str) -> dict:
    """Compute three-gate metrics for one quadrant.

    trades_net: per-trade NET (post-fee) returns
    pool_gross: gross fwd_log_ret pool (will be multiplied by +/-1 depending
                on direction_label for null comparison)
    """
    if len(trades_net) < 30:
        return {"n": int(len(trades_net)), "error": "n<30"}

    # Apply direction sign convention to pool: pool is raw fwd_log_ret;
    # for LONG quadrants null = pool * (+1); for SHORT quadrants null = pool * (-1)
    if direction_label in ("A_focus_LONG", "B_mirror_LONG"):
        pool_directed = pool_gross.copy()
    else:
        pool_directed = -pool_gross.copy()

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
        "ci_upper_bp": (boot["ci_upper"] * 10000.0 if not pd.isna(boot["ci_upper"]) else float("nan")),
        "prob_positive": boot["prob_positive"],
        "gate_excess": gate_excess,
        "gate_ci": gate_ci,
        "gate_perm": gate_perm,
        "three_gate_pass": three_gate_pass,
    }


def concentration_diagnostics(trig_df: pd.DataFrame, direction_filter: int,
                              direction_sign: int, name: str) -> dict:
    """Per-quarter t + per-symbol bootstrap for Concentration Gate (Lesson #16)."""
    subset = trig_df[trig_df["direction"] == direction_filter].copy()
    if subset.empty:
        return {"name": name, "n": 0, "error": "empty"}
    # net per-trade in bp
    subset["net_bp"] = subset["fwd_log_ret_4h"] * direction_sign * 10000.0 - FEE_BP

    # per-quarter t
    per_qtr_t = {}
    for q, grp in subset.groupby("qtr"):
        if len(grp) >= 10:
            arr = grp["net_bp"].values
            sd = arr.std(ddof=1)
            t_q = float(arr.mean() / (sd / math.sqrt(len(arr)))) if sd > 0 else 0.0
            per_qtr_t[q] = {"n": int(len(grp)), "t": t_q,
                            "mean_bp": float(arr.mean())}
    n_measurable_q = len(per_qtr_t)
    n_pos_q = sum(1 for v in per_qtr_t.values() if v["t"] > 0)
    quarter_pos_t_ratio = (n_pos_q / n_measurable_q) if n_measurable_q else 0.0

    # per-symbol bootstrap CI
    per_sym_ci = {}
    for s, grp in subset.groupby("sym"):
        if len(grp) >= 20:
            net = grp["net_bp"].values / 10000.0  # back to dec
            boot = bootstrap_ci(net, n_boot=1000, block_size=1)
            per_sym_ci[s] = {
                "n": int(len(grp)),
                "ci_lower_bp": float(boot["ci_lower"] * 10000.0) if not pd.isna(boot["ci_lower"]) else None,
                "ci_pos": bool(boot["ci_lower"] > 0) if not pd.isna(boot["ci_lower"]) else False,
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
    log.info("triggers: total=%d (pos=%d / neg=%d)", len(trig_df),
             int((trig_df["direction"] > 0).sum()),
             int((trig_df["direction"] < 0).sum()))

    if len(trig_df) < 100:
        log.error("insufficient triggers (n=%d < 100) — graveyard", len(trig_df))
        sys.exit(2)

    pool_gross = build_candidate_pool(panel)
    log.info("candidate pool: n=%d (unconditional fwd_log_ret_4h)", len(pool_gross))

    # Build per-quadrant trade arrays
    pos_trig = trig_df[trig_df["direction"] > 0].copy()
    neg_trig = trig_df[trig_df["direction"] < 0].copy()

    # A_focus: pos × LONG  (net = +fwd - fee)
    a_focus_net = (pos_trig["fwd_log_ret_4h"].values * (+1.0)) - FEE_PER_TRADE
    # A_mirror: pos × SHORT (net = -fwd - fee)
    a_mirror_net = (pos_trig["fwd_log_ret_4h"].values * (-1.0)) - FEE_PER_TRADE
    # B_focus: neg × SHORT (net = -fwd - fee)
    b_focus_net = (neg_trig["fwd_log_ret_4h"].values * (-1.0)) - FEE_PER_TRADE
    # B_mirror: neg × LONG (net = +fwd - fee)
    b_mirror_net = (neg_trig["fwd_log_ret_4h"].values * (+1.0)) - FEE_PER_TRADE

    log.info("--- Evaluating 4 quadrants ---")
    quadrants = {
        "A_focus_park_p90_pos_LONG_4h": (a_focus_net, "A_focus_LONG"),
        "A_mirror_park_p90_pos_SHORT_4h": (a_mirror_net, "A_mirror_SHORT"),
        "B_focus_park_p90_neg_SHORT_4h": (b_focus_net, "B_focus_SHORT"),
        "B_mirror_park_p90_neg_LONG_4h": (b_mirror_net, "B_mirror_LONG"),
    }
    quad_results = {}
    for qname, (trades, dlabel) in quadrants.items():
        res = evaluate_quadrant(trades, pool_gross, dlabel)
        quad_results[qname] = res
        if "error" in res:
            log.warning("  %s: %s", qname, res)
        else:
            log.info("  %s: n=%d gross=%.2fbp net=%.2fbp "
                     "obs_t=%.2f null_t=%.2f sigex=%.2f ci_lower=%.2fbp perm_p=%.3f "
                     "3gate=%s (excess=%s ci=%s perm=%s)",
                     qname, res["n"], res["gross_bp"], res["net_bp"],
                     res["obs_t"], res["null_mean_t"], res["signal_t_excess"],
                     res["ci_lower_bp"], res["perm_p_one_sided_above"],
                     res["three_gate_pass"], res["gate_excess"], res["gate_ci"],
                     res["gate_perm"])

    # Concentration diagnostics for each quadrant
    log.info("--- Concentration diagnostics (Lesson #16) ---")
    conc_results = {}
    conc_specs = [
        ("A_focus_LONG", +1, +1),  # direction_filter, direction_sign
        ("A_mirror_SHORT", +1, -1),
        ("B_focus_SHORT", -1, -1),
        ("B_mirror_LONG", -1, +1),
    ]
    for name, dfilter, dsign in conc_specs:
        c = concentration_diagnostics(trig_df, dfilter, dsign, name)
        conc_results[name] = c
        if "error" in c:
            log.warning("  conc %s: %s", name, c)
        else:
            log.info("  conc %s: n=%d q_pos_t=%d/%d ratio=%.2f sym_ci_pos=%d/%d ratio=%.2f "
                     "concentration_gate=%s",
                     name, c["n_total"], c["n_pos_q"], c["n_measurable_q"],
                     c["quarter_pos_t_ratio"], c["n_ci_pos"], c["n_measurable_sym"],
                     c["symbol_ci_pos_ratio"], c["concentration_gate_pass"])

    # Verdict
    pass_quadrants = [q for q, r in quad_results.items()
                      if r.get("three_gate_pass", False)]
    log.info("=== R-1 PASSING quadrants: %s ===", pass_quadrants if pass_quadrants else "NONE")

    # Determine verdict per Lesson #39 sub-classes
    # Sub-class A: focus + mirror BOTH negative (broad uniform negative) -> direction-bet noise
    # Sub-class B: focus negative + mirror positive concentration -> fee floor mechanism inverted
    # Sub-class C: focus positive but concentration fail -> narrow
    def is_neg(q):
        r = quad_results.get(q, {})
        return r.get("net_bp", 0) < 0 and not r.get("three_gate_pass", False)

    def is_pos(q):
        r = quad_results.get(q, {})
        return r.get("three_gate_pass", False)

    a_focus_neg = is_neg("A_focus_park_p90_pos_LONG_4h")
    a_mirror_neg = is_neg("A_mirror_park_p90_pos_SHORT_4h")
    b_focus_neg = is_neg("B_focus_park_p90_neg_SHORT_4h")
    b_mirror_neg = is_neg("B_mirror_park_p90_neg_LONG_4h")

    a_focus_pos = is_pos("A_focus_park_p90_pos_LONG_4h")
    b_mirror_pos = is_pos("B_mirror_park_p90_neg_LONG_4h")
    a_mirror_pos = is_pos("A_mirror_park_p90_pos_SHORT_4h")
    b_focus_pos = is_pos("B_focus_park_p90_neg_SHORT_4h")

    if not pass_quadrants:
        if a_focus_neg and a_mirror_neg and b_focus_neg and b_mirror_neg:
            verdict = "BROAD_FALSIFIED_BOTH_FOCUS_NEGATIVE"
            sub_class = "A_broad_uniform_negative_no_axis_synthesis (Lesson #39 sub-class A)"
        elif a_focus_neg and a_mirror_neg:
            verdict = "BROAD_FALSIFIED_A_FOCUS_NEGATIVE"
            sub_class = "A pair both negative (mechanism direction inverted or noise)"
        elif b_focus_neg and b_mirror_neg:
            verdict = "BROAD_FALSIFIED_B_FOCUS_NEGATIVE"
            sub_class = "B pair both negative (mechanism direction inverted or noise)"
        else:
            verdict = "BROAD_FALSIFIED_MIXED"
            sub_class = "mixed quadrant negativity"
    else:
        # At least one quadrant PASS — check concentration
        passing_with_conc = []
        for q in pass_quadrants:
            conc_key = q.split("_park_p90_")[0] + "_" + q.split("_4h")[0].split("_")[-1]
            # Map quadrant name to conc result key
            if "pos_LONG" in q:
                ckey = "A_focus_LONG"
            elif "pos_SHORT" in q:
                ckey = "A_mirror_SHORT"
            elif "neg_SHORT" in q:
                ckey = "B_focus_SHORT"
            elif "neg_LONG" in q:
                ckey = "B_mirror_LONG"
            else:
                ckey = None
            if ckey and conc_results.get(ckey, {}).get("concentration_gate_pass", False):
                passing_with_conc.append((q, ckey))

        if passing_with_conc:
            verdict = "PASS_R1_FULL"
            sub_class = f"three-gate PASS + Concentration Gate PASS: {[p[0] for p in passing_with_conc]}"
        else:
            verdict = "CONCENTRATED_R1_PASS"
            sub_class = f"three-gate PASS but Concentration FAIL: {pass_quadrants}"

    log.info("=== VERDICT: %s ===", verdict)
    log.info("=== SUB-CLASS: %s ===", sub_class)

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
            "park_rolling_bars_4h": PARK_ROLLING_BARS_4H,
            "park_percentile": PARK_PERCENTILE,
            "forward_hold_4h_bars": FORWARD_HOLD_4H_BARS,
            "debounce_hours": DEBOUNCE_HOURS,
            "fee_per_trade": FEE_PER_TRADE,
            "fee_bp": FEE_BP,
            "n_perms": N_PERMS,
            "n_boot": N_BOOT,
        },
        "universe_loaded": list(panel.keys()),
        "n_triggers_total": int(len(trig_df)),
        "n_triggers_pos": int((trig_df["direction"] > 0).sum()),
        "n_triggers_neg": int((trig_df["direction"] < 0).sum()),
        "candidate_pool_n": int(len(pool_gross)),
        "quadrant_results": quad_results,
        "concentration_diagnostics": conc_results,
    }

    out_path = OUT_DIR / "r1__metrics.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    log.info("R-1 saved to %s", out_path)


if __name__ == "__main__":
    main()
