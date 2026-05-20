"""paradigm 122 R-1 — `intraday_session_open_alt_oi_acceleration_directional_30m`.

Trigger: 13 alt 5m OI velocity z-score top-decile (|z| ≥ per-sym p90) at DUAL ANCHOR
  - Anchor 1: CME equity close ±15min around 21:00 UTC
  - Anchor 2: Funding-cycle clock ±5min around 00:00 / 08:00 / 16:00 UTC
Forward hold: 30min sign-matched (positive OI velocity → LONG, negative → SHORT)

4-quadrant Symmetric Negative Test (Lesson #19):
  A_focus  : top-decile pos × LONG  (continuation hypothesis)
  A_mirror : top-decile pos × SHORT (mean-revert hypothesis)
  B_focus  : top-decile neg × SHORT (continuation hypothesis)
  B_mirror : top-decile neg × LONG  (mean-revert hypothesis)

Statistical tests (Lessons #5, #16, #19, #21, #32, #39, #41):
  - fee_aware_perm_test (16bp round-trip fee)
  - bootstrap_ci (block size 6 = 30min)
  - per-quarter / per-symbol concentration
  - Lesson #39 sub-class A/B/C manual detection
  - Lesson #41 amendment: per-trade edge ≥ 2% GATE FIRST, sigex/DIFFUSE_POSITIVE SECOND
"""
from __future__ import annotations

import json
import logging
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

sys.path.insert(0, "/home/hcpark/antigravity/backend")
from scripts.research._perm_utils import bootstrap_ci, fee_aware_perm_test

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("p122_r1")

OUT_DIR = Path("/home/hcpark/antigravity/backend/runs/research_track/intraday_session_open_alt_oi_acceleration_directional_30m")
OUT_DIR.mkdir(parents=True, exist_ok=True)

COHORT = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT",
    "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

ANCHOR_CME_HR_UTC = 21
ANCHOR_CME_HALF_WIN_MIN = 15
ANCHOR_FUND_HRS_UTC = [0, 8, 16]
ANCHOR_FUND_HALF_WIN_MIN = 5
ROLL_WIN_BARS = 30 * 24 * 12
FORWARD_HOLD_BARS = 6  # 30min
FEE_RT_PCT = 0.0016  # 16bp round-trip (assumed)
DECILE_PCT = 0.90


def load_ohlcv_5m(sym: str, engine) -> pd.DataFrame:
    q = text("SELECT timestamp, close FROM ohlcv WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp")
    df = pd.read_sql(q, engine, params={"s": sym}, parse_dates=["timestamp"])
    if df.empty:
        return df
    df = df.set_index("timestamp")
    return df["close"].resample("5min").last().dropna().to_frame()


def load_oi(sym: str) -> pd.Series:
    p = f"/home/hcpark/antigravity/backend/runs/microstructure/{sym}_full_metrics.joblib"
    if not os.path.exists(p):
        return pd.Series(dtype=float)
    df = joblib.load(p)
    return df["open_interest"].copy() if "open_interest" in df.columns else pd.Series(dtype=float)


def build_panel():
    dsn = "postgresql://antigravity_user:antigravity_password@localhost:5432/antigravity_db"
    eng = create_engine(dsn)
    rows = []
    for sym in COHORT:
        log.info("loading %s", sym)
        oh = load_ohlcv_5m(sym, eng)
        oi = load_oi(sym)
        if oh.empty or oi.empty:
            log.warning("skip %s (oh=%s oi=%s)", sym, oh.empty, oi.empty)
            continue
        j = oh.join(oi, how="inner").dropna()
        if len(j) < ROLL_WIN_BARS + 100:
            continue
        j["oi_ret"] = j["open_interest"].pct_change()
        rm = j["oi_ret"].rolling(ROLL_WIN_BARS, min_periods=ROLL_WIN_BARS // 2).mean()
        rs = j["oi_ret"].rolling(ROLL_WIN_BARS, min_periods=ROLL_WIN_BARS // 2).std()
        j["oi_vel_z"] = (j["oi_ret"] - rm) / rs
        j["fwd_ret"] = j["close"].pct_change(FORWARD_HOLD_BARS).shift(-FORWARD_HOLD_BARS)
        j["sym"] = sym
        j = j.dropna(subset=["oi_vel_z", "fwd_ret"])
        rows.append(j)
    panel = pd.concat(rows).sort_index()

    # anchors
    mod = panel.index.hour * 60 + panel.index.minute
    cme = np.abs(mod - ANCHOR_CME_HR_UTC * 60) <= ANCHOR_CME_HALF_WIN_MIN
    fund = np.zeros(len(panel), dtype=bool)
    for h in ANCHOR_FUND_HRS_UTC:
        d = np.abs(mod - h * 60)
        d = np.minimum(d, 24 * 60 - d)
        fund |= (d <= ANCHOR_FUND_HALF_WIN_MIN)
    panel["in_cme"] = cme
    panel["in_fund"] = fund
    panel["in_dual"] = cme | fund

    # per-sym p90 |z|
    panel["abs_z"] = panel["oi_vel_z"].abs()
    p90 = panel.groupby("sym")["abs_z"].transform(lambda s: s.quantile(DECILE_PCT))
    panel["is_top_decile"] = panel["abs_z"] >= p90
    panel["trigger"] = panel["is_top_decile"] & panel["in_dual"]
    panel["qtr"] = panel.index.to_period("Q").astype(str)
    return panel


def quadrant_stats(panel, focus_pos_long: bool, focus_pos: bool):
    """Compute quadrant statistics with full R-1 protocol.
    focus_pos: True for pos-z trigger arm, False for neg-z arm
    focus_pos_long: True for sign-matched LONG (focus quadrant), False for mirror (SHORT)
    """
    if focus_pos:
        sub = panel[panel["trigger"] & (panel["oi_vel_z"] > 0)].copy()
    else:
        sub = panel[panel["trigger"] & (panel["oi_vel_z"] < 0)].copy()
    if focus_pos:
        sub["direction"] = 1 if focus_pos_long else -1
    else:
        sub["direction"] = -1 if focus_pos_long else 1
    sub["gross_ret"] = sub["fwd_ret"] * sub["direction"]
    sub["net_ret"] = sub["gross_ret"] - FEE_RT_PCT
    return sub


def candidate_pool(panel):
    """All non-triggered fwd returns for the perm pool (gross, no direction applied)."""
    return panel.loc[~panel["trigger"], "fwd_ret"].dropna().values


def compute_quadrant(name: str, sub: pd.DataFrame, pool_gross: np.ndarray):
    n = len(sub)
    if n < 30:
        return {"label": name, "n": n, "error": "n<30"}
    net = sub["net_ret"].values
    gross_mean = float(sub["gross_ret"].mean()) * 10000
    net_mean = float(net.mean()) * 10000
    sd = float(sub["net_ret"].std(ddof=1)) * 10000
    t = net_mean / (sd / math.sqrt(n)) if sd > 0 else 0.0

    # fee-aware perm: candidate pool needs to be matched to direction — use |gross| equivalent
    # because mirror is just sign flip, the perm pool used here is the gross fwd_ret pool, which
    # the perm test will fee-adjust. Direction is encoded in observed net. For valid comparison,
    # generate pool with random sign matched per draw.
    # Simpler approach (sign-matched): apply observed direction to a random subset of pool.
    rng = np.random.default_rng(42)
    if len(pool_gross) >= n * 2:
        # construct directional pool: for each draw of size n, randomly assign ±1 directions
        pool_with_dir = pool_gross * rng.choice([-1, 1], size=len(pool_gross))
        pool_net = pool_with_dir - FEE_RT_PCT
        perm = fee_aware_perm_test(
            observed_net_returns=net,
            candidate_pool_returns=pool_with_dir,
            fee_per_trade=FEE_RT_PCT,
            n_perms=1000,
            rng_seed=42,
        )
    else:
        perm = {"signal_t_excess": float("nan"), "perm_p_two_sided": float("nan")}

    ci = bootstrap_ci(net, n_boot=2000, block_size=6, alpha=0.05)
    # convert to bp
    ci_lower_bp = ci["ci_lower"] * 10000
    ci_upper_bp = ci["ci_upper"] * 10000
    ci_mean_bp = ci["mean"] * 10000

    # 3-gate
    sigex = perm.get("signal_t_excess", float("nan"))
    perm_p = perm.get("perm_p_two_sided", float("nan"))
    gate_sigex = (not math.isnan(sigex)) and sigex >= 2.0
    gate_ci = (not math.isnan(ci_lower_bp)) and ci_lower_bp > 0
    gate_perm = (not math.isnan(perm_p)) and perm_p <= 0.10
    three_gate = gate_sigex and gate_ci and gate_perm

    # Concentration: per-quarter t, per-symbol bootstrap
    per_q_t = {}
    n_pos_t_q = 0
    n_measurable_q = 0
    for q, grp in sub.groupby("qtr"):
        if len(grp) < 30:
            continue
        n_measurable_q += 1
        gn = grp["net_ret"].values * 10000
        gs = gn.std(ddof=1)
        gt = gn.mean() / (gs / math.sqrt(len(gn))) if gs > 0 else 0.0
        per_q_t[q] = float(gt)
        if gt > 0:
            n_pos_t_q += 1
    quarter_pos_t_ratio = n_pos_t_q / n_measurable_q if n_measurable_q > 0 else 0.0

    per_sym = {}
    n_ci_pos_sym = 0
    n_measurable_sym = 0
    for s, grp in sub.groupby("sym"):
        if len(grp) < 30:
            continue
        n_measurable_sym += 1
        gn = grp["net_ret"].values
        bs = bootstrap_ci(gn, n_boot=1000, block_size=6, alpha=0.05)
        cl_bp = bs["ci_lower"] * 10000
        per_sym[s] = {"n": int(len(grp)), "mean_bp": float(grp["net_ret"].mean()) * 10000,
                      "ci_lower_bp": float(cl_bp), "ci_pos": bool(cl_bp > 0)}
        if cl_bp > 0:
            n_ci_pos_sym += 1
    symbol_ci_pos_ratio = n_ci_pos_sym / n_measurable_sym if n_measurable_sym > 0 else 0.0

    conc_gate = (quarter_pos_t_ratio >= 0.5) and (symbol_ci_pos_ratio >= 0.30) and (n_ci_pos_sym >= 3)

    # Lesson #32 universe-baseline-coherent: per-quarter baseline drift (whole panel same hold)
    # measured separately if focus FAIL with concentration

    return {
        "label": name,
        "n": int(n),
        "gross_bp": gross_mean,
        "net_bp": net_mean,
        "obs_t": float(t),
        "signal_t_excess": float(sigex) if not math.isnan(sigex) else None,
        "perm_p_two": float(perm_p) if not math.isnan(perm_p) else None,
        "ci_mean_bp": float(ci_mean_bp),
        "ci_lower_bp": float(ci_lower_bp),
        "ci_upper_bp": float(ci_upper_bp),
        "ci_prob_pos": float(ci["prob_positive"]),
        "gate_sigex_pass": bool(gate_sigex),
        "gate_ci_pass": bool(gate_ci),
        "gate_perm_pass": bool(gate_perm),
        "three_gate_pass": bool(three_gate),
        "concentration": {
            "n_measurable_quarters": int(n_measurable_q),
            "n_pos_t_quarters": int(n_pos_t_q),
            "quarter_pos_t_ratio": float(quarter_pos_t_ratio),
            "per_quarter_t": per_q_t,
            "n_measurable_symbols": int(n_measurable_sym),
            "n_ci_pos_symbols": int(n_ci_pos_sym),
            "symbol_ci_pos_ratio": float(symbol_ci_pos_ratio),
            "per_symbol": per_sym,
            "concentration_gate_pass": bool(conc_gate),
        },
    }


def lesson_39_sub_class(focus: dict, mirror: dict, mirror_concentration: dict):
    """Detect Lesson #39 sub-class A/B/C.

    Sub-class A: both focus + mirror gross broad-uniform-negative (after fee)
                 → no directional info, joint signal pure direction-bet
    Sub-class B: focus broad-uniform-negative, mirror shows real concentration
                 (mirror q_pos_t >= 30% or syms_ci_pos >= 30%)
                 → mechanism direction inverted, real but fee-bound
    Sub-class C: mixed (no symmetric pattern matched)
    """
    if focus.get("error") or mirror.get("error"):
        return {"sub_class": "indeterminate", "note": "n<30 in quadrant"}
    f_gross = focus.get("gross_bp")
    m_gross = mirror.get("gross_bp")
    sym_sum = f_gross + m_gross if (f_gross is not None and m_gross is not None) else None
    exact_sym = (sym_sum is not None) and (abs(sym_sum) < 0.5)  # by construction sign-matched mirror

    # focus broad-uniform-negative?
    fn_neg = focus.get("net_bp") < 0
    f_conc = focus.get("concentration", {})
    f_broad = (f_conc.get("symbol_ci_pos_ratio", 0) < 0.10) and fn_neg

    # mirror real concentration?
    m_real = (mirror_concentration.get("quarter_pos_t_ratio", 0) >= 0.30) or \
             (mirror_concentration.get("symbol_ci_pos_ratio", 0) >= 0.30)

    if exact_sym and f_broad and not m_real:
        return {"sub_class": "A_broad_uniform_negative",
                "note": "trigger has zero directional info; joint signal = direction-bet + fee drag",
                "exact_symmetric": True, "focus_broad_negative": True, "mirror_real_concentration": False}
    if exact_sym and f_broad and m_real:
        return {"sub_class": "B_mechanism_inverted",
                "note": "mechanism direction is mirror (real but fee-bound); original direction inverted",
                "exact_symmetric": True, "focus_broad_negative": True, "mirror_real_concentration": True}
    return {"sub_class": "C_asymmetric_or_unmatched",
            "note": "no clean sub-class A/B signature",
            "exact_symmetric": bool(exact_sym), "focus_broad_negative": bool(f_broad),
            "mirror_real_concentration": bool(m_real)}


def life_changing(quad: dict, panel_days: float):
    if quad.get("error") or quad.get("n", 0) < 30:
        return {"applicable": False}
    n = quad["n"]
    per_yr = n / (panel_days / 365.0)
    per_trade_edge_pct = quad.get("net_bp", 0) / 100.0  # bp → %
    # capital util: assume hold 30min, slots-per-day = 48, panel 13 syms × 48 slots × days
    # naive: triggers / total possible slots
    capital_util_pct = float("nan")  # leave for downstream
    # sharpe approximation: t * sqrt(yr/N)
    obs_t = quad.get("obs_t", 0)
    sharpe_approx = obs_t * math.sqrt(per_yr / n) if n > 0 else 0
    return {
        "applicable": True,
        "trades_per_year": float(per_yr),
        "per_trade_edge_pct": float(per_trade_edge_pct),
        "annualized_sharpe_approx": float(sharpe_approx),
        "gate_trades_per_year_ge_12": bool(per_yr >= 12),
        "gate_edge_ge_2pct": bool(per_trade_edge_pct >= 2.0),
        "gate_sharpe_ge_1p5": bool(sharpe_approx >= 1.5),
        "lesson_41_amendment_edge_first_pass": bool(per_trade_edge_pct >= 2.0),
    }


def main():
    log.info("paradigm 122 R-1 start (KST %s)", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    panel = build_panel()
    log.info("panel: %d bars", len(panel))
    panel_days = (panel.index.max() - panel.index.min()).days
    log.info("panel days: %d", panel_days)

    pool = candidate_pool(panel)
    log.info("candidate pool (non-trigger fwd ret): %d", len(pool))

    # 4 quadrants
    quads = {}
    quads["A_focus_pos_LONG"] = compute_quadrant("A_focus_pos_LONG",
        quadrant_stats(panel, focus_pos_long=True, focus_pos=True), pool)
    quads["A_mirror_pos_SHORT"] = compute_quadrant("A_mirror_pos_SHORT",
        quadrant_stats(panel, focus_pos_long=False, focus_pos=True), pool)
    quads["B_focus_neg_SHORT"] = compute_quadrant("B_focus_neg_SHORT",
        quadrant_stats(panel, focus_pos_long=False, focus_pos=False), pool)
    quads["B_mirror_neg_LONG"] = compute_quadrant("B_mirror_neg_LONG",
        quadrant_stats(panel, focus_pos_long=True, focus_pos=False), pool)

    for k, q in quads.items():
        if "error" in q:
            log.info("%s: %s", k, q)
            continue
        log.info("%s n=%d gross=%.2fbp net=%.2fbp t=%.2f sigex=%s ci=[%.2f, %.2f] perm_p=%s 3gate=%s qpos=%.2f spos=%.2f conc=%s",
                 k, q["n"], q["gross_bp"], q["net_bp"], q["obs_t"],
                 f"{q['signal_t_excess']:.2f}" if q["signal_t_excess"] is not None else "NA",
                 q["ci_lower_bp"], q["ci_upper_bp"],
                 f"{q['perm_p_two']:.3f}" if q["perm_p_two"] is not None else "NA",
                 q["three_gate_pass"],
                 q["concentration"]["quarter_pos_t_ratio"], q["concentration"]["symbol_ci_pos_ratio"],
                 q["concentration"]["concentration_gate_pass"])

    # Lesson #39 sub-class
    sub_a = lesson_39_sub_class(quads["A_focus_pos_LONG"], quads["A_mirror_pos_SHORT"], quads["A_mirror_pos_SHORT"].get("concentration", {}))
    sub_b = lesson_39_sub_class(quads["B_focus_neg_SHORT"], quads["B_mirror_neg_LONG"], quads["B_mirror_neg_LONG"].get("concentration", {}))
    log.info("Lesson #39 sub-class A-arm: %s", sub_a)
    log.info("Lesson #39 sub-class B-arm: %s", sub_b)

    # Life-changing 4-dim
    lc = {k: life_changing(q, panel_days) for k, q in quads.items()}
    for k, v in lc.items():
        if v.get("applicable"):
            log.info("%s life-changing: trades/yr=%.1f edge=%.4f%% sharpe=%.2f edge_first=%s",
                     k, v["trades_per_year"], v["per_trade_edge_pct"],
                     v["annualized_sharpe_approx"], v["lesson_41_amendment_edge_first_pass"])

    # Overall verdict
    any_three_gate = any(q.get("three_gate_pass", False) for q in quads.values() if "error" not in q)
    any_conc_pass = any(q.get("concentration", {}).get("concentration_gate_pass", False) for q in quads.values() if "error" not in q)
    any_life_changing = any(v.get("lesson_41_amendment_edge_first_pass", False) for v in lc.values())

    if any_three_gate and any_conc_pass and any_life_changing:
        verdict = "PASS_R1_FULL_LIFE_CHANGING"
    elif any_three_gate and any_conc_pass:
        verdict = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
    elif any_three_gate:
        verdict = "CONCENTRATED_R1_PASS"
    else:
        # Check focus broad-uniform-negative (Lesson #39 sub-class)
        a_focus = quads["A_focus_pos_LONG"]
        b_focus = quads["B_focus_neg_SHORT"]
        if not a_focus.get("error") and not b_focus.get("error"):
            if a_focus.get("net_bp", 0) < 0 and b_focus.get("net_bp", 0) < 0:
                verdict = "BROAD_FALSIFIED_BOTH_FOCUS_NEGATIVE"
            elif a_focus.get("net_bp", 0) < 0 or b_focus.get("net_bp", 0) < 0:
                verdict = "BROAD_FALSIFIED_PARTIAL"
            else:
                verdict = "BROAD_FALSIFIED_NO_THREE_GATE"
        else:
            verdict = "BROAD_FALSIFIED_NO_THREE_GATE"

    # Lesson #44 amendment xref
    lesson_44 = {
        "paradigm_113_hour_of_day_anchor": "BROAD_FALSIFIED 2026-05-20 (hour-anchor alone -6.69bp, 0/13 syms ci_pos)",
        "paradigm_71_oi_velocity_single": "BROAD_FALSIFIED (OI velocity alone, 0/3 z thresholds PASS)",
        "paradigm_120_oi_x_btc_regime": "BROAD_FALSIFIED (OI velocity × BTC regime, 0/13 alts × 4/4 cluster fail)",
        "lesson_21_two_null_axes": "paradigm 71 OI alone + paradigm 113 hour-anchor alone = 2 null axes; stacking risk per Lesson #21",
        "family_implication": "If paradigm 122 BROAD_FALSIFIED → 3rd OI velocity sub-class → oi_velocity_directional_family Tier 4 retire candidate",
    }

    out = {
        "paradigm_name": "intraday_session_open_alt_oi_acceleration_directional_30m",
        "counter": 122,
        "phase": "R-1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "panel": {
            "n_bars": int(len(panel)),
            "panel_days": int(panel_days),
            "n_symbols": int(panel["sym"].nunique()),
            "n_triggers_pos": int((panel["trigger"] & (panel["oi_vel_z"] > 0)).sum()),
            "n_triggers_neg": int((panel["trigger"] & (panel["oi_vel_z"] < 0)).sum()),
            "trigger_rate_pct": round(float(panel["trigger"].mean()) * 100, 4),
        },
        "fee_rt_pct": FEE_RT_PCT,
        "decile_pct": DECILE_PCT,
        "anchors": {"cme_hr_utc": ANCHOR_CME_HR_UTC, "cme_half_win_min": ANCHOR_CME_HALF_WIN_MIN,
                    "fund_hrs_utc": ANCHOR_FUND_HRS_UTC, "fund_half_win_min": ANCHOR_FUND_HALF_WIN_MIN},
        "forward_hold_min": 30,
        "quadrants": quads,
        "lesson_39_sub_class": {
            "A_arm": sub_a,
            "B_arm": sub_b,
        },
        "lesson_41_amendment_life_changing_4dim": lc,
        "lesson_44_amendment_graveyard_xref": lesson_44,
        "verdict": verdict,
    }

    out_path = OUT_DIR / "r1__metrics.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    log.info("R-1 metrics: %s", out_path)
    log.info("VERDICT: %s", verdict)


if __name__ == "__main__":
    main()
