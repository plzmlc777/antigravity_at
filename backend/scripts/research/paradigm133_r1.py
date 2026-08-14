"""paradigm 133 R-1 PoC — alt_realized_vol_of_vol_2nd_order_clustering_regime_directional_4h.

4-quadrant SNT (Lesson #19 mandatory):
  A_focus  = trigger ∩ direction>0 × LONG  (RV-of-RV spike on up-bar -> momentum continuation)
  A_mirror = trigger ∩ direction>0 × SHORT (RV-of-RV spike on up-bar -> fade)
  B_focus  = trigger ∩ direction<0 × SHORT (RV-of-RV spike on down-bar -> momentum continuation)
  B_mirror = trigger ∩ direction<0 × LONG  (RV-of-RV spike on down-bar -> reversion)

R-1 three-gate per quadrant:
  signal_t_excess >= 2.0 AND ci_lower > 0 AND perm_p_one_sided <= 0.10

Concentration Gate (Lesson #16):
  quarter_pos_t_ratio >= 0.5 AND symbol_ci_pos_ratio >= 0.30 AND n_symbols_ci_pos >= 3

R-0 advisory:
  A_focus per-quarter signs [+,-,-,+] (2 flips, alternating)
  B_focus per-quarter signs [-,+,-,-] (2 flips, alternating)
  Stratified gross: A_focus -30bp / B_focus -50bp / mirrors both +30~+50bp
  HYPOTHESIS REFRAMING: focus (momentum continuation) -> FAIL likely
                       mirror (mean-reversion / fade) -> potentially PASS
  Lesson #52a/b + Lesson #53 candidate detection enabled at R-1.
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
log = logging.getLogger("p133_r1")

PARADIGM_NAME = "alt_realized_vol_of_vol_2nd_order_clustering_regime_directional_4h"
PARADIGM_NUM = 133
OUT_DIR = Path(f"/home/hcpark/antigravity/backend/runs/research_track/{PARADIGM_NAME}")
OUT_DIR.mkdir(parents=True, exist_ok=True)

COHORT = [
    "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT",
    "NEARUSDT", "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

RV_WINDOW_5M_PER_1H = 12
RVOV_ROLLING_HOURS = 24
ZSCORE_ROLLING_HOURS = 30 * 24
Z_THRESHOLD = 2.0
FORWARD_HOLD_4H_BARS = 1
DEBOUNCE_HOURS = 8
FEE_PER_TRADE = 0.0016  # 16bp round-trip
FEE_BP = FEE_PER_TRADE * 10000.0
N_PERMS = 1000
N_BOOT = 2000
DB_DSN = "postgresql://antigravity_user:antigravity_password@localhost:5432/antigravity_db"


def load_ohlcv_1m(sym: str, engine) -> pd.DataFrame:
    q = text(
        "SELECT timestamp, close FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
    )
    df = pd.read_sql(q, engine, params={"s": sym}, parse_dates=["timestamp"])
    if df.empty:
        return df
    df = df.set_index("timestamp")
    return df


def compute_rv_1h(df_1m: pd.DataFrame) -> pd.Series:
    close_5m = df_1m["close"].resample("5min").last().dropna()
    log_ret_5m = np.log(close_5m / close_5m.shift(1))
    sq_ret_5m = log_ret_5m ** 2
    sum_sq_1h = sq_ret_5m.resample("1h").sum(min_count=8)
    rv_1h = np.sqrt(sum_sq_1h)
    return rv_1h.dropna()


def compute_rvov_z(rv_1h: pd.Series) -> tuple[pd.Series, pd.Series]:
    rvov = rv_1h.rolling(window=RVOV_ROLLING_HOURS, min_periods=18).std()
    rvov_mean = rvov.rolling(window=ZSCORE_ROLLING_HOURS, min_periods=240).mean()
    rvov_std = rvov.rolling(window=ZSCORE_ROLLING_HOURS, min_periods=240).std()
    z = (rvov - rvov_mean) / rvov_std
    return rvov, z


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
        rv_1h = compute_rv_1h(df)
        if len(rv_1h) < ZSCORE_ROLLING_HOURS + RVOV_ROLLING_HOURS:
            log.warning("%s skip insufficient RV", sym)
            continue
        rvov, z = compute_rvov_z(rv_1h)
        bar4h = aggregate_to_4h(df)
        z_4h = z.resample("4h").max().dropna()
        bar4h = bar4h.copy()
        bar4h["z_rvov"] = z_4h.reindex(bar4h.index, method="ffill")
        bar4h["fwd_log_ret_4h"] = bar4h["log_ret_4h"].shift(-FORWARD_HOLD_4H_BARS)
        bar4h["cond"] = bar4h["z_rvov"] > Z_THRESHOLD
        bar4h["sym"] = sym
        panels[sym] = bar4h
    engine.dispose()
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
                "z_rvov": float(row["z_rvov"]),
                "direction": d,
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
                      direction_label: str) -> dict:
    if len(trades_net) < 30:
        return {"n": int(len(trades_net)), "error": "n<30"}

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
    subset = trig_df[trig_df["direction"] == direction_filter].copy()
    if subset.empty:
        return {"name": name, "n": 0, "error": "empty"}
    subset["net_bp"] = subset["fwd_log_ret_4h"] * direction_sign * 10000.0 - FEE_BP

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

    pos_trig = trig_df[trig_df["direction"] > 0].copy()
    neg_trig = trig_df[trig_df["direction"] < 0].copy()

    a_focus_net = (pos_trig["fwd_log_ret_4h"].values * (+1.0)) - FEE_PER_TRADE
    a_mirror_net = (pos_trig["fwd_log_ret_4h"].values * (-1.0)) - FEE_PER_TRADE
    b_focus_net = (neg_trig["fwd_log_ret_4h"].values * (-1.0)) - FEE_PER_TRADE
    b_mirror_net = (neg_trig["fwd_log_ret_4h"].values * (+1.0)) - FEE_PER_TRADE

    log.info("--- Evaluating 4 quadrants ---")
    quadrants = {
        "A_focus_z2_pos_LONG_4h": (a_focus_net, "A_focus_LONG"),
        "A_mirror_z2_pos_SHORT_4h": (a_mirror_net, "A_mirror_SHORT"),
        "B_focus_z2_neg_SHORT_4h": (b_focus_net, "B_focus_SHORT"),
        "B_mirror_z2_neg_LONG_4h": (b_mirror_net, "B_mirror_LONG"),
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

    log.info("--- Concentration diagnostics (Lesson #16) ---")
    conc_results = {}
    conc_specs = [
        ("A_focus_LONG", +1, +1),
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

    pass_quadrants = [q for q, r in quad_results.items()
                      if r.get("three_gate_pass", False)]
    log.info("=== R-1 PASSING quadrants: %s ===", pass_quadrants if pass_quadrants else "NONE")

    def is_neg(q):
        r = quad_results.get(q, {})
        return r.get("net_bp", 0) < 0 and not r.get("three_gate_pass", False)

    def is_pos(q):
        r = quad_results.get(q, {})
        return r.get("three_gate_pass", False)

    a_focus_neg = is_neg("A_focus_z2_pos_LONG_4h")
    a_mirror_neg = is_neg("A_mirror_z2_pos_SHORT_4h")
    b_focus_neg = is_neg("B_focus_z2_neg_SHORT_4h")
    b_mirror_neg = is_neg("B_mirror_z2_neg_LONG_4h")

    a_focus_pos = is_pos("A_focus_z2_pos_LONG_4h")
    b_mirror_pos = is_pos("B_mirror_z2_neg_LONG_4h")
    a_mirror_pos = is_pos("A_mirror_z2_pos_SHORT_4h")
    b_focus_pos = is_pos("B_focus_z2_neg_SHORT_4h")

    # Lesson #52a/b detection: both LONG quadrants positive (A_focus_LONG + B_mirror_LONG)
    # while concentration low (0 syms ci_pos universal pattern)
    a_focus_net_bp = quad_results.get("A_focus_z2_pos_LONG_4h", {}).get("net_bp", 0)
    b_mirror_net_bp = quad_results.get("B_mirror_z2_neg_LONG_4h", {}).get("net_bp", 0)
    a_focus_conc_n = conc_results.get("A_focus_LONG", {}).get("n_ci_pos", 0)
    b_mirror_conc_n = conc_results.get("B_mirror_LONG", {}).get("n_ci_pos", 0)
    lesson_52_pattern = bool(
        a_focus_net_bp > 0 and b_mirror_net_bp > 0
        and a_focus_conc_n == 0 and b_mirror_conc_n == 0
    )

    # Lesson #53 candidate: hypothesis dir (focus) vs mirror dir comparison
    # If focus FAIL + mirror PASS (or much stronger gross), hypothesis direction inverted
    a_focus_gross = quad_results.get("A_focus_z2_pos_LONG_4h", {}).get("gross_bp", 0)
    a_mirror_gross = quad_results.get("A_mirror_z2_pos_SHORT_4h", {}).get("gross_bp", 0)
    b_focus_gross = quad_results.get("B_focus_z2_neg_SHORT_4h", {}).get("gross_bp", 0)
    b_mirror_gross = quad_results.get("B_mirror_z2_neg_LONG_4h", {}).get("gross_bp", 0)
    lesson_53_a_inverted = a_focus_gross < 0 and a_mirror_gross > 0 and (a_mirror_gross - a_focus_gross > 20)
    lesson_53_b_inverted = b_focus_gross < 0 and b_mirror_gross > 0 and (b_mirror_gross - b_focus_gross > 20)

    if not pass_quadrants:
        if a_focus_neg and a_mirror_neg and b_focus_neg and b_mirror_neg:
            verdict = "BROAD_FALSIFIED_BOTH_FOCUS_NEGATIVE"
            sub_class = "A_broad_uniform_negative_no_axis_synthesis (Lesson #39 sub-class A)"
        elif a_focus_neg and b_focus_neg:
            if lesson_53_a_inverted and lesson_53_b_inverted:
                verdict = "BROAD_FALSIFIED_MIRROR_DIRECTION_INVERTED"
                sub_class = "Lesson #39 sub-class B variant — both focus negative, both mirrors positive (direction-inverted but still sub-fee)"
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
    log.info("Lesson #52 a/b pattern (both LONG pos + 0 syms ci_pos): %s", lesson_52_pattern)
    log.info("Lesson #53 A direction inverted (focus<0, mirror>0, gap>20bp): %s", lesson_53_a_inverted)
    log.info("Lesson #53 B direction inverted (focus<0, mirror>0, gap>20bp): %s", lesson_53_b_inverted)

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
            "rv_window_5m_per_1h": RV_WINDOW_5M_PER_1H,
            "rvov_rolling_hours": RVOV_ROLLING_HOURS,
            "zscore_rolling_hours": ZSCORE_ROLLING_HOURS,
            "z_threshold": Z_THRESHOLD,
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
        "lesson_52_a_b_pattern": lesson_52_pattern,
        "lesson_53_a_direction_inverted": lesson_53_a_inverted,
        "lesson_53_b_direction_inverted": lesson_53_b_inverted,
    }

    out_path = OUT_DIR / "r1__metrics.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    log.info("R-1 saved to %s", out_path)


if __name__ == "__main__":
    main()
