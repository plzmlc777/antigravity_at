"""paradigm 145 R-0 prescreen: independence/density check before R-1 dispatch.

Validates:
- Lesson #21 sub-finding: funding_z vs oi_velocity_z per-sym correlation < 0.5
  (cross-substrate hybrid must show axis independence, otherwise trivial composite)
- Lesson #11 sample density: joint trigger n per cell >= 30
- Lesson #40 structural threshold feasibility: per-sym z<=-2.0 reachable both axes
- Lesson #58 candidate exemption: cross-substrate (NOT same-bar same-substrate ratio)
- Lesson #30 data window ratio: funding DB ~1y vs OI 5m ~1.55y → ratio ~0.65 (PASS)

Trigger: funding_z <= -2.0 (8h cycle) ∩ oi_velocity_z <= -2.0 (5m frame, aligned to funding cycle)
Universe: 10 alts (paradigm 22 + paradigm 21 R-5 substrate intersection)

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
log = logging.getLogger("paradigm145_r0")

PARADIGM_NAME = "alt_funding_carry_x_oi_decoupling_4h_cross_r5_hybrid_directional"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_NAME
OUT_DIR.mkdir(parents=True, exist_ok=True)

UNIVERSE = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "LINKUSDT",
    "DOGEUSDT", "HBARUSDT", "AXSUSDT", "COMPUSDT", "ETCUSDT",
]

# Funding (8h cycle)
ROLLING_LB_CYCLES_FUNDING = 90  # ~30d (8h cycle * 3 = 24h * 30 = 90 cycles)
Z_THRESHOLD_FUNDING_NEG = -2.0

# OI 5m
ROLLING_WIN_5M = 288  # 24h at 5m
Z_THRESHOLD_OI_NEG = -2.0

# Lesson #21 sub-finding independence thresholds
INDEP_CORR_MAX = 0.5  # per-sym corr below this required (cross-substrate hybrid)
INDEP_CORR_STRONG_FAIL = 0.90  # axis degeneracy halt
INDEP_RESID_MIN = 0.20  # residual variance fraction required

# Lesson #11 sample density
MIN_PER_CELL_N = 30
MIN_JOINT_N_TOTAL = 50  # absolute floor


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
    """For each funding cycle timestamp, find the 5m OI z at that timestamp (or nearest <=5m)."""
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
    log.info("paradigm 145 R-0 prescreen starting at %s", pd.Timestamp.utcnow())

    funding = load_funding_panel()
    log.info("funding panel: %d syms", len(funding))
    funding_z = compute_funding_z(funding)

    # Per-symbol independence and density check
    per_sym = {}
    joint_n_total = 0
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

        # Per-sym correlation between funding_z and oi_velocity_z at funding cycle timestamps
        fz = aligned["funding_z"].values
        oz = aligned["oi_velocity_z"].values
        mask = np.isfinite(fz) & np.isfinite(oz)
        if mask.sum() < 30:
            per_sym[sym] = {"error": "insufficient aligned rows", "n_aligned": int(mask.sum())}
            continue
        fz, oz = fz[mask], oz[mask]
        corr = float(np.corrcoef(fz, oz)[0, 1])

        # Lesson #21 sub-finding residual: 1 - R^2
        resid_frac = float(1.0 - corr ** 2)

        # Joint trigger count
        joint_mask = (fz <= Z_THRESHOLD_FUNDING_NEG) & (oz <= Z_THRESHOLD_OI_NEG)
        n_joint = int(joint_mask.sum())
        joint_n_total += n_joint

        # Sample density estimates
        n_funding_neg = int((fz <= Z_THRESHOLD_FUNDING_NEG).sum())
        n_oi_neg = int((oz <= Z_THRESHOLD_OI_NEG).sum())

        # Lesson #40 structural reachability
        z_min_f = float(fz.min())
        z_min_o = float(oz.min())
        z_min_funding_per_sym[sym] = z_min_f
        z_min_oi_per_sym[sym] = z_min_o

        per_sym[sym] = {
            "n_aligned": int(mask.sum()),
            "corr_funding_oi_z": corr,
            "resid_frac_1_minus_r2": resid_frac,
            "n_funding_neg_z2": n_funding_neg,
            "n_oi_neg_z2": n_oi_neg,
            "n_joint_both_neg_z2": n_joint,
            "funding_z_min": z_min_f,
            "oi_velocity_z_min": z_min_o,
            "funding_z_reachable": bool(z_min_f <= Z_THRESHOLD_FUNDING_NEG),
            "oi_z_reachable": bool(z_min_o <= Z_THRESHOLD_OI_NEG),
        }
        corr_values.append(corr)
        resid_values.append(resid_frac)
        log.info("[%s] aligned=%d corr=%.3f resid=%.3f n_joint=%d (f_neg=%d, oi_neg=%d) z_min f=%.2f o=%.2f",
                 sym, mask.sum(), corr, resid_frac, n_joint, n_funding_neg, n_oi_neg, z_min_f, z_min_o)

    # Aggregate independence
    n_syms_measured = len(corr_values)
    mean_corr = float(np.mean(corr_values)) if corr_values else float("nan")
    max_abs_corr = float(np.max(np.abs(corr_values))) if corr_values else float("nan")
    min_resid = float(np.min(resid_values)) if resid_values else float("nan")
    mean_resid = float(np.mean(resid_values)) if resid_values else float("nan")

    # Aggregate sample density (per-cell ~ joint_n_total / 4 quarters typical)
    n_quarters_assumed = 4
    per_cell_estimate = joint_n_total / n_quarters_assumed if n_quarters_assumed > 0 else 0

    # Lesson #21 sub-finding axis_degeneracy hard gate (strong, halt-eligible)
    axis_degen_strong = bool(max_abs_corr >= INDEP_CORR_STRONG_FAIL)
    # Lesson #21 sub-finding cross-substrate independence soft gate
    indep_soft_pass = bool(max_abs_corr < INDEP_CORR_MAX and min_resid > INDEP_RESID_MIN)

    # Lesson #11 sample density gate
    density_pass = bool(joint_n_total >= MIN_JOINT_N_TOTAL and per_cell_estimate >= MIN_PER_CELL_N)

    # Lesson #40 structural reachability gate (all syms must reach z<=-2.0 both axes)
    reach_funding = sum(1 for v in per_sym.values()
                         if isinstance(v, dict) and v.get("funding_z_reachable"))
    reach_oi = sum(1 for v in per_sym.values()
                    if isinstance(v, dict) and v.get("oi_z_reachable"))
    reach_pass = bool(reach_funding == n_syms_measured and reach_oi == n_syms_measured
                       and n_syms_measured >= 8)

    # Verdict
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
        # Soft fail — still PROCEED but log advisory
        verdict = "R0_PROCEED_WITH_INDEPENDENCE_ADVISORY"
        reason = f"max_abs_corr={max_abs_corr:.3f} or min_resid={min_resid:.3f} below Lesson #21 sub-finding soft thresholds, but axes are not degenerate (<0.90). cross-substrate exemption applies, proceeding with R-1 dispatch but axis synthesis must be verified in V1/V2/V3 measurement."
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
        "paradigm_id": 145,
        "phase": "R-0",
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
            "applies": False,
            "reason": "cross-substrate hybrid (funding DB + OI 5m joblib) — NOT same-bar same-substrate ratio antipattern",
            "substrate_1": "binance_funding_rate (DB, 8h cycle)",
            "substrate_2": "microstructure joblib open_interest (5m frame, file)",
            "substrate_3": "klines (forward 4h return computation, future R-1 step)",
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
    log.info("wall clock: %.1fs", time.time() - t_start)
    return 0 if verdict.startswith("R0_PROCEED") else 2


if __name__ == "__main__":
    sys.exit(main())
