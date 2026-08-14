"""paradigm 146 R-0 prescreen: relaxed funding_z (-1.0) + universe 15.

Repairs paradigm 145 sparse-joint failure (n_joint=15, per_cell=3.75) by:
- Relaxing funding threshold -2.0 → -1.0 (~16% base rate vs ~4.5%)
- Expanding universe 10 → 15 (paradigm 145 + ICP/UNI/LDO/WLD/1000LUNC; AAVE excluded — funding DB unavailable)
- Keeping OI threshold strict -2.0 (paradigm 21 R-5 alignment)
- Direction SHORT 4h continuation (paradigm 22 R-5 mirror direction — Lesson #56 5th dogfood opportunity)

Validates:
- Lesson #21 sub-finding independence (cross-substrate)
- Lesson #11 sample density (relaxed thresholds calculation precise, paradigm 145 10x estimation error 회피 의무)
- Lesson #40 structural threshold feasibility per-sym
- Lesson #58 candidate cross-substrate exemption (3 substrates: funding DB + OI joblib + klines)
- Lesson #30 data window ratio (funding 1y binding)

Output: r0_prescreen.json (HALT/PROCEED verdict)
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("paradigm146_r0")

PARADIGM_NAME = "alt_funding_z_neg1_x_oi_z_neg2_4h_relaxed_universe15_short"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_NAME
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Universe expanded paradigm 145 base + 5 (AAVE excluded — funding DB unavailable)
UNIVERSE = [
    # paradigm 145 base 10
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "LINKUSDT",
    "DOGEUSDT", "HBARUSDT", "AXSUSDT", "COMPUSDT", "ETCUSDT",
    # paradigm 146 additions 5
    "ICPUSDT", "UNIUSDT", "LDOUSDT", "WLDUSDT", "1000LUNCUSDT",
]

# Funding (8h cycle) — RELAXED threshold
ROLLING_LB_CYCLES_FUNDING = 90  # ~30d
Z_THRESHOLD_FUNDING_NEG = -1.0  # relaxed from -2.0 (paradigm 145)

# OI 5m — STRICT (paradigm 21 R-5 alignment)
ROLLING_WIN_5M = 288  # 24h at 5m
Z_THRESHOLD_OI_NEG = -2.0

# Lesson #21 sub-finding independence
INDEP_CORR_MAX = 0.5
INDEP_CORR_STRONG_FAIL = 0.90
INDEP_RESID_MIN = 0.20

# Lesson #11 sample density
MIN_PER_CELL_N = 30
MIN_JOINT_N_TOTAL = 50


def load_funding_panel() -> Dict[str, pd.DataFrame]:
    db = SessionLocal()
    out: Dict[str, pd.DataFrame] = {}
    try:
        for sym in UNIVERSE:
            rows = db.execute(
                text(
                    "SELECT funding_time, funding_rate FROM binance_funding_rate "
                    "WHERE symbol=:s ORDER BY funding_time"
                ),
                {"s": sym},
            ).fetchall()
            if not rows:
                continue
            df = pd.DataFrame(rows, columns=["t", "rate"])
            df["t"] = pd.to_datetime(df["t"])
            df["rate"] = df["rate"].astype(float)
            df = df.drop_duplicates(subset=["t"]).sort_values("t").reset_index(drop=True)
            out[sym] = df
    finally:
        db.close()
    return out


def compute_funding_z(funding: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    out = {}
    for sym, df in funding.items():
        d = df.copy()
        d["mu"] = d["rate"].rolling(ROLLING_LB_CYCLES_FUNDING, min_periods=int(ROLLING_LB_CYCLES_FUNDING * 0.5)).mean().shift(1)
        d["sd"] = d["rate"].rolling(ROLLING_LB_CYCLES_FUNDING, min_periods=int(ROLLING_LB_CYCLES_FUNDING * 0.5)).std(ddof=1).shift(1)
        d["funding_z"] = (d["rate"] - d["mu"]) / d["sd"].replace(0, np.nan)
        d = d.dropna(subset=["funding_z"])
        out[sym] = d[["t", "rate", "funding_z"]].reset_index(drop=True)
    return out


def load_oi_5m_z(sym: str) -> pd.DataFrame | None:
    p = ROOT / "runs" / "microstructure" / f"{sym}_full_metrics.joblib"
    if not p.exists():
        return None
    df = joblib.load(p)
    oi = df["open_interest"].copy().where(df["open_interest"] > 0, np.nan)
    dlog = np.log(oi).diff()
    mu = dlog.rolling(ROLLING_WIN_5M, min_periods=ROLLING_WIN_5M // 2).mean()
    sd = dlog.rolling(ROLLING_WIN_5M, min_periods=ROLLING_WIN_5M // 2).std(ddof=1)
    z = (dlog - mu) / sd.replace(0, np.nan)
    z = z.replace([np.inf, -np.inf], np.nan)
    out = pd.DataFrame({"oi_velocity_z": z})
    return out.dropna()


def align_funding_to_oi_5m(funding_df: pd.DataFrame, oi_df: pd.DataFrame) -> pd.DataFrame:
    f = funding_df.copy()
    o = oi_df.copy()
    o.index = pd.to_datetime(o.index)
    o = o.sort_index()
    f["t"] = pd.to_datetime(f["t"])
    f = f.sort_values("t").reset_index(drop=True)
    aligned_oiz = []
    for ts in f["t"]:
        pos = o.index.searchsorted(ts, side="left")
        if pos >= len(o.index):
            aligned_oiz.append(np.nan)
            continue
        candidate_idx = o.index[pos]
        if (candidate_idx - ts).total_seconds() <= 300:
            aligned_oiz.append(float(o["oi_velocity_z"].iloc[pos]))
        elif pos > 0:
            prev = o.index[pos - 1]
            if (ts - prev).total_seconds() <= 300:
                aligned_oiz.append(float(o["oi_velocity_z"].iloc[pos - 1]))
            else:
                aligned_oiz.append(np.nan)
        else:
            aligned_oiz.append(np.nan)
    f["oi_velocity_z"] = aligned_oiz
    return f.dropna(subset=["oi_velocity_z"])


def main() -> int:
    t_start = time.time()
    log.info("paradigm 146 R-0 prescreen starting at %s", pd.Timestamp.utcnow())
    log.info("universe %d syms, funding_z<=%.1f, oi_z<=%.1f", len(UNIVERSE), Z_THRESHOLD_FUNDING_NEG, Z_THRESHOLD_OI_NEG)

    funding = load_funding_panel()
    log.info("funding panel loaded: %d/%d syms", len(funding), len(UNIVERSE))
    funding_z = compute_funding_z(funding)

    per_sym = {}
    joint_n_total = 0
    n_funding_neg_total = 0
    n_oi_neg_total = 0
    corr_values = []
    resid_values = []
    z_min_funding_per_sym = {}
    z_min_oi_per_sym = {}

    for sym in UNIVERSE:
        if sym not in funding_z:
            per_sym[sym] = {"error": "no funding data"}
            continue
        oi_df = load_oi_5m_z(sym)
        if oi_df is None or oi_df.empty:
            per_sym[sym] = {"error": "no OI data"}
            continue
        aligned = align_funding_to_oi_5m(funding_z[sym], oi_df)
        if aligned.empty:
            per_sym[sym] = {"error": "alignment empty"}
            continue

        fz = aligned["funding_z"].values
        oz = aligned["oi_velocity_z"].values
        mask = np.isfinite(fz) & np.isfinite(oz)
        if mask.sum() < 30:
            per_sym[sym] = {"error": "insufficient aligned rows", "n_aligned": int(mask.sum())}
            continue
        fz, oz = fz[mask], oz[mask]
        corr = float(np.corrcoef(fz, oz)[0, 1])
        resid_frac = float(1.0 - corr ** 2)

        joint_mask = (fz <= Z_THRESHOLD_FUNDING_NEG) & (oz <= Z_THRESHOLD_OI_NEG)
        n_joint = int(joint_mask.sum())
        joint_n_total += n_joint

        n_funding_neg = int((fz <= Z_THRESHOLD_FUNDING_NEG).sum())
        n_oi_neg = int((oz <= Z_THRESHOLD_OI_NEG).sum())
        n_funding_neg_total += n_funding_neg
        n_oi_neg_total += n_oi_neg

        z_min_f = float(fz.min())
        z_min_o = float(oz.min())
        z_min_funding_per_sym[sym] = z_min_f
        z_min_oi_per_sym[sym] = z_min_o

        # Base rates for sanity check (paradigm 145 10x estimation error 회피)
        n_total = int(mask.sum())
        funding_base_rate = n_funding_neg / n_total if n_total > 0 else 0.0
        oi_base_rate = n_oi_neg / n_total if n_total > 0 else 0.0
        expected_joint_indep = funding_base_rate * oi_base_rate * n_total
        joint_lift = (n_joint / max(expected_joint_indep, 1e-9)) if expected_joint_indep > 0 else float("nan")

        per_sym[sym] = {
            "n_aligned": n_total,
            "corr_funding_oi_z": corr,
            "resid_frac_1_minus_r2": resid_frac,
            "n_funding_neg_z1": n_funding_neg,
            "funding_base_rate": funding_base_rate,
            "n_oi_neg_z2": n_oi_neg,
            "oi_base_rate": oi_base_rate,
            "n_joint": n_joint,
            "joint_base_rate": n_joint / n_total if n_total > 0 else 0.0,
            "expected_joint_indep_count": expected_joint_indep,
            "joint_lift_vs_indep": joint_lift,
            "funding_z_min": z_min_f,
            "oi_velocity_z_min": z_min_o,
            "funding_z_reachable": bool(z_min_f <= Z_THRESHOLD_FUNDING_NEG),
            "oi_z_reachable": bool(z_min_o <= Z_THRESHOLD_OI_NEG),
        }
        corr_values.append(corr)
        resid_values.append(resid_frac)
        log.info("[%s] aligned=%d corr=%.3f resid=%.3f n_joint=%d (f_neg=%d/%.1f%%, oi_neg=%d/%.1f%%) lift=%.2fx",
                 sym, n_total, corr, resid_frac, n_joint, n_funding_neg, funding_base_rate * 100,
                 n_oi_neg, oi_base_rate * 100, joint_lift)

    n_syms_measured = len(corr_values)
    mean_corr = float(np.mean(corr_values)) if corr_values else float("nan")
    max_abs_corr = float(np.max(np.abs(corr_values))) if corr_values else float("nan")
    min_resid = float(np.min(resid_values)) if resid_values else float("nan")
    mean_resid = float(np.mean(resid_values)) if resid_values else float("nan")

    n_quarters_assumed = 4
    per_cell_estimate = joint_n_total / n_quarters_assumed if n_quarters_assumed > 0 else 0

    axis_degen_strong = bool(max_abs_corr >= INDEP_CORR_STRONG_FAIL)
    indep_soft_pass = bool(max_abs_corr < INDEP_CORR_MAX and min_resid > INDEP_RESID_MIN)
    density_pass = bool(joint_n_total >= MIN_JOINT_N_TOTAL and per_cell_estimate >= MIN_PER_CELL_N)

    reach_funding = sum(1 for v in per_sym.values()
                        if isinstance(v, dict) and v.get("funding_z_reachable"))
    reach_oi = sum(1 for v in per_sym.values()
                   if isinstance(v, dict) and v.get("oi_z_reachable"))
    reach_pass = bool(reach_funding == n_syms_measured and reach_oi == n_syms_measured
                      and n_syms_measured >= 10)

    if axis_degen_strong:
        verdict = "R0_HALT_STRUCTURAL_AXIS_DEGENERACY"
        reason = f"max_abs_corr={max_abs_corr:.3f} >= {INDEP_CORR_STRONG_FAIL} (Lesson #21 sub-finding hard halt)"
    elif not density_pass:
        verdict = "R0_HALT_SAMPLE_INSUFFICIENT"
        reason = f"joint_n_total={joint_n_total} or per_cell_estimate={per_cell_estimate:.1f} < {MIN_PER_CELL_N} (Lesson #11)"
    elif not reach_pass:
        verdict = "R0_HALT_STRUCTURAL_THRESHOLD_INFEASIBLE"
        reason = f"funding_reachable={reach_funding}/{n_syms_measured} oi_reachable={reach_oi}/{n_syms_measured} (Lesson #40)"
    elif not indep_soft_pass:
        verdict = "R0_PROCEED_WITH_INDEPENDENCE_ADVISORY"
        reason = (f"max_abs_corr={max_abs_corr:.3f} or min_resid={min_resid:.3f} below Lesson #21 sub-finding "
                  f"soft thresholds, but axes are not degenerate (<0.90). cross-substrate exemption applies, "
                  f"proceeding with R-1 dispatch but axis synthesis must be verified in V1/V2/V3 measurement.")
    else:
        verdict = "R0_PROCEED"
        reason = (
            f"All gates PASS: max_abs_corr={max_abs_corr:.3f} < {INDEP_CORR_MAX}, "
            f"min_resid={min_resid:.3f} > {INDEP_RESID_MIN}, "
            f"joint_n_total={joint_n_total} per_cell~{per_cell_estimate:.1f}, "
            f"reach f={reach_funding}/{n_syms_measured} oi={reach_oi}/{n_syms_measured}"
        )

    out = {
        "paradigm_name": PARADIGM_NAME,
        "paradigm_id": 146,
        "phase": "R-0",
        "parent_paradigm": 145,
        "repair_strategy": "relaxed funding_z -2.0 → -1.0 + universe 10 → 15",
        "lesson_56_candidate_dogfood": "5th instance (paradigm 22 R-5 LONG MR mirror → SHORT continuation)",
        "lesson_21_dogfood": "6th instance (V1/V2/V3 individual-vs-joint sigex 결정적 측정 의무, R-1 단계)",
        "run_ts": str(pd.Timestamp.utcnow()),
        "wall_clock_seconds": float(time.time() - t_start),
        "config": {
            "universe": UNIVERSE,
            "n_syms_universe": len(UNIVERSE),
            "n_syms_measured": n_syms_measured,
            "rolling_lb_cycles_funding": ROLLING_LB_CYCLES_FUNDING,
            "rolling_win_5m_oi": ROLLING_WIN_5M,
            "z_threshold_funding_neg": Z_THRESHOLD_FUNDING_NEG,
            "z_threshold_oi_neg": Z_THRESHOLD_OI_NEG,
        },
        "lesson_21_sub_finding_independence": {
            "per_sym_corr": {s: per_sym[s].get("corr_funding_oi_z") for s in per_sym
                             if isinstance(per_sym[s], dict) and "corr_funding_oi_z" in per_sym[s]},
            "per_sym_resid_frac": {s: per_sym[s].get("resid_frac_1_minus_r2") for s in per_sym
                                   if isinstance(per_sym[s], dict) and "resid_frac_1_minus_r2" in per_sym[s]},
            "mean_corr": mean_corr,
            "max_abs_corr": max_abs_corr,
            "mean_resid": mean_resid,
            "min_resid": min_resid,
            "indep_corr_max_threshold": INDEP_CORR_MAX,
            "indep_corr_strong_fail_threshold": INDEP_CORR_STRONG_FAIL,
            "indep_resid_min_threshold": INDEP_RESID_MIN,
            "axis_degen_strong_halt": axis_degen_strong,
            "indep_soft_pass": indep_soft_pass,
        },
        "lesson_11_sample_density": {
            "joint_n_total": int(joint_n_total),
            "n_funding_neg_total": int(n_funding_neg_total),
            "n_oi_neg_total": int(n_oi_neg_total),
            "n_quarters_assumed": int(n_quarters_assumed),
            "per_cell_estimate": float(per_cell_estimate),
            "min_per_cell_n": int(MIN_PER_CELL_N),
            "min_joint_n_total": int(MIN_JOINT_N_TOTAL),
            "density_pass": density_pass,
        },
        "lesson_40_structural_threshold_feasibility": {
            "n_syms_funding_reachable": int(reach_funding),
            "n_syms_oi_reachable": int(reach_oi),
            "n_syms_measured": int(n_syms_measured),
            "funding_z_min_per_sym": z_min_funding_per_sym,
            "oi_velocity_z_min_per_sym": z_min_oi_per_sym,
            "reach_pass": reach_pass,
        },
        "lesson_58_candidate_exemption": {
            "applies": True,
            "reason": "cross-substrate hybrid (funding DB + OI 5m joblib + klines forward) — 3 substrates",
            "substrate_1": "binance_funding_rate (DB, 8h cycle)",
            "substrate_2": "microstructure joblib open_interest (5m frame)",
            "substrate_3": "klines (forward 4h return)",
        },
        "lesson_30_data_window_ratio": {
            "funding_span_estimated_days": 365,
            "oi_span_estimated_days": 730,
            "ratio_funding_vs_oi": 0.5,
            "binding_substrate": "funding (1y, limiting factor)",
            "advisory": "verdict scoped to funding-available window",
        },
        "per_symbol": per_sym,
        "verdict": verdict,
        "reason": reason,
    }

    out_path = OUT_DIR / "r0_prescreen.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    log.info("wrote %s", out_path)
    log.info("=== R-0 VERDICT: %s ===", verdict)
    log.info("=== REASON: %s ===", reason)
    log.info("joint_n_total=%d per_cell_est=%.1f", joint_n_total, per_cell_estimate)
    log.info("wall clock: %.1fs", time.time() - t_start)
    return 0 if verdict.startswith("R0_PROCEED") else 2


if __name__ == "__main__":
    sys.exit(main())
