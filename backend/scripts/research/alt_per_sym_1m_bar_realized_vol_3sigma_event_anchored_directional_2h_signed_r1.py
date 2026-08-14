"""paradigm 207 R-1 PoC.

Hypothesis
----------
Per-sym 1h-rolling realized volatility (from 1m bars) z-score ≥ +3 event spike,
anchored by the 1m bar's directional sign, predicts +2h/+4h/+8h forward signed
direction. 4-quadrant Symmetric Negative Test with **disjoint trigger sets**
(bar UP vs bar DOWN partition cell A and cell B → cell A∩B = ∅).

Cells:
- A focus    : rv_z ≥ +3 × bar UP × LONG continuation
- A mirror   : rv_z ≥ +3 × bar UP × SHORT reversal
- B same-sign: rv_z ≥ +3 × bar DOWN × SHORT continuation  (DISJOINT trigger from A)
- B mirror   : rv_z ≥ +3 × bar DOWN × LONG reversal      (Lesson #42 15th dogfood)

Lesson coverage
---------------
- #11 sample density: prescreen confirms ~1.5-1.8% trigger rate × 18 syms × 2.25yr → ~9000/cell.
- #19 SNT: 4-quadrant in single batch.
- #28 substrate-shape: 1m DB cache 18/20 syms × 2.25yr verified.
- #34 empirical distribution: prescreen confirms +8h DOGE A_focus +61.5bp, multi-sym viable.
- #39 sub-class A explicit avoidance: cell A bar UP, cell B bar DOWN → disjoint partition.
- #40 structural threshold: rv is non-negative aggregate, z≥+3 only (z≤-3 infeasible);
  one-sided trigger is correct construction.
- #42 15th dogfood: B mirror cell measured separately.
- #69 Item 7 SNT structural integrity 2nd operational dogfood:
  cross-set |A_focus| vs |B_same| asymmetric (prescreen DOGE +8h shows |+61.5| vs |-65.2| ≈ 1.06x;
  per-sym variance high — final magnitudes pending full run).
- Lesson candidate post-206: trigger temporal cluster analysis +
  per-symbol concentration check mandatory.
- Era stratify (Item 6, 4-pattern taxonomy): 2024/2025/2026 per-quadrant.

Universe
--------
18 alts (paradigm 198 cohort minus ADAUSDT (143d cache only) and BTCUSDT (excluded as
mechanism is per-sym alt idiosyncratic NOT BTC-anchored cross-asset).
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.core.config import settings  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _perm_utils import fee_aware_perm_test, bootstrap_ci  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("paradigm_207_r1")

# === Config ===
PARADIGM_ID = 207
PARADIGM_NAME = "alt_per_sym_1m_bar_realized_vol_3sigma_event_anchored_directional_2h_signed"
OUT_DIR = Path("/home/hcpark/antigravity/backend/runs/research_track") / PARADIGM_NAME
OUT_DIR.mkdir(parents=True, exist_ok=True)

UNIVERSE = [
    "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT", "DOTUSDT",
    "ETCUSDT", "ETHUSDT", "FILUSDT", "JUPUSDT", "LDOUSDT",
    "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT", "UNIUSDT",
    "WIFUSDT", "WLDUSDT", "XRPUSDT",
]  # 18 alts; ADAUSDT (143d) and BTCUSDT (per-sym alt mechanism) excluded

RV_WINDOW_BARS = 60        # 1h realized vol from 1m bars
Z_WINDOW_BARS = 30 * 1440  # 30d rolling z-score window
Z_THRESHOLD = 3.0
HOLDS_MIN = [120, 240, 480]   # +2h primary, +4h sweep, +8h sweep
FEE_PER_TRADE = 0.0008        # 8bp one-way → 16bp round-trip
N_PERMS = 1000
N_BOOT = 2000

# Gate constants
SIGNAL_T_EXCESS_PASS = 2.0
CI_LOWER_PASS_BP = 0.0
PERM_P_PASS = 0.10
QUARTER_POS_T_RATIO_PASS = 0.5
SYMBOL_CI_POS_RATIO_PASS = 0.30
SYMBOL_CI_POS_N_PASS = 3


def load_sym_1m(sym: str) -> pd.DataFrame:
    """Load 1m OHLCV from DB for a single sym."""
    conn = psycopg2.connect(
        host=settings.POSTGRES_SERVER, user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD, dbname=settings.POSTGRES_DB,
    )
    cur = conn.cursor()
    cur.execute(
        "SELECT timestamp, close FROM ohlcv WHERE symbol=%s AND time_frame='1m' ORDER BY timestamp",
        (sym,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["ts", "close"])
    df["close"] = df["close"].astype(float)
    df = df.set_index("ts").sort_index()
    return df


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute log_ret, rv_1h, rv_z, bar_sign, forward returns."""
    df = df.copy()
    df["log_ret"] = np.log(df["close"]).diff()
    df["rv_1h"] = np.sqrt((df["log_ret"] ** 2).rolling(RV_WINDOW_BARS).sum())
    df["rv_mean"] = df["rv_1h"].rolling(Z_WINDOW_BARS, min_periods=10 * 1440).mean()
    df["rv_std"] = df["rv_1h"].rolling(Z_WINDOW_BARS, min_periods=10 * 1440).std()
    df["rv_z"] = (df["rv_1h"] - df["rv_mean"]) / df["rv_std"]
    df["trigger"] = df["rv_z"] >= Z_THRESHOLD
    df["bar_sign"] = np.sign(df["log_ret"]).fillna(0)
    for hold in HOLDS_MIN:
        df[f"fwd_{hold}m"] = (np.log(df["close"].shift(-hold)) - np.log(df["close"])) * 10000  # bp
    return df


def build_quadrant_returns(df: pd.DataFrame, hold: int):
    """Return per-cell net (post-fee, in bp) and gross arrays per quadrant.

    Quadrants:
      A_focus : bar_sign > 0 × LONG  → +fwd  (continuation)
      A_mirror: bar_sign > 0 × SHORT → -fwd  (reversal)
      B_same  : bar_sign < 0 × SHORT → -fwd  (continuation; DISJOINT trigger from A)
      B_mirror: bar_sign < 0 × LONG  → +fwd  (reversal; Lesson #42)
    """
    fwd_col = f"fwd_{hold}m"
    trig = df[df["trigger"] & df[fwd_col].notna()].copy()
    fee_bp = FEE_PER_TRADE * 2 * 10000  # 16bp round-trip
    cells = {}
    pos_mask = trig["bar_sign"] > 0
    neg_mask = trig["bar_sign"] < 0
    cells["A_focus"] = {
        "gross_bp": trig.loc[pos_mask, fwd_col].values,
        "net_bp": trig.loc[pos_mask, fwd_col].values - fee_bp,
        "ts": trig.loc[pos_mask].index.values,
    }
    cells["A_mirror"] = {
        "gross_bp": -trig.loc[pos_mask, fwd_col].values,
        "net_bp": -trig.loc[pos_mask, fwd_col].values - fee_bp,
        "ts": trig.loc[pos_mask].index.values,
    }
    cells["B_same"] = {
        "gross_bp": -trig.loc[neg_mask, fwd_col].values,
        "net_bp": -trig.loc[neg_mask, fwd_col].values - fee_bp,
        "ts": trig.loc[neg_mask].index.values,
    }
    cells["B_mirror"] = {
        "gross_bp": trig.loc[neg_mask, fwd_col].values,
        "net_bp": trig.loc[neg_mask, fwd_col].values - fee_bp,
        "ts": trig.loc[neg_mask].index.values,
    }
    # Candidate pool = all fwd returns (non-trigger fwd_col, both directions)
    pool = df[df[fwd_col].notna()][fwd_col].values
    return cells, pool


def t_stat(arr: np.ndarray) -> float:
    if len(arr) < 2:
        return 0.0
    s = np.std(arr, ddof=1)
    if s == 0 or not np.isfinite(s):
        return 0.0
    return float(np.mean(arr) / s * np.sqrt(len(arr)))


def era_of(ts) -> str:
    if isinstance(ts, np.datetime64):
        ts = pd.Timestamp(ts).to_pydatetime()
    y = ts.year
    return f"era_{y}"


def quarter_of(ts) -> str:
    if isinstance(ts, np.datetime64):
        ts = pd.Timestamp(ts).to_pydatetime()
    return f"{ts.year}Q{(ts.month - 1) // 3 + 1}"


def main():
    log.info("paradigm 207 R-1 PoC start  universe=%d holds=%s z>=+%.1f", len(UNIVERSE), HOLDS_MIN, Z_THRESHOLD)
    log.info("OUT_DIR=%s", OUT_DIR)

    # 1) Load per-sym data
    per_sym = {}
    for sym in UNIVERSE:
        df = load_sym_1m(sym)
        if df.empty:
            log.warning("skip %s — no data", sym); continue
        df = compute_features(df)
        per_sym[sym] = df
        n_trig = int(df["trigger"].sum())
        log.info("%s  n_bars=%d  n_trigger=%d  (%.4f%%)", sym, len(df), n_trig, 100 * n_trig / len(df))

    # 2) Per-cell aggregate metrics + per-symbol bootstrap CI + per-quarter t + per-era t
    cells_agg = {c: {"net_bp": [], "gross_bp": [], "ts": [], "per_sym": {}, "per_quarter": {}, "per_era": {}}
                 for c in ["A_focus", "A_mirror", "B_same", "B_mirror"]}

    for sym, df in per_sym.items():
        cells_h2, pool_h2 = build_quadrant_returns(df, 120)
        for cell_name, cell_data in cells_h2.items():
            ca = cells_agg[cell_name]
            ca["net_bp"].extend(cell_data["net_bp"].tolist())
            ca["gross_bp"].extend(cell_data["gross_bp"].tolist())
            ca["ts"].extend(cell_data["ts"].tolist())
            ca["per_sym"][sym] = cell_data["net_bp"].tolist()

    # Aggregate cell stats at +2h (primary hold)
    metrics = {"paradigm_id": PARADIGM_ID, "paradigm_name": PARADIGM_NAME,
               "run_ts_kst": (datetime.now(timezone.utc) + timedelta(hours=9)).isoformat(),
               "hold_primary_min": 120, "z_threshold": Z_THRESHOLD,
               "universe_n": len(per_sym), "universe": list(per_sym.keys()),
               "rv_window_bars": RV_WINDOW_BARS, "z_window_bars": Z_WINDOW_BARS,
               "fee_per_trade": FEE_PER_TRADE, "fee_round_trip_bp": FEE_PER_TRADE * 2 * 10000,
               "cells": {}}

    log.info("=== R-1 4-QUADRANT SNT AGGREGATE (primary hold +120m) ===")
    for cell_name, ca in cells_agg.items():
        net_arr = np.array(ca["net_bp"])
        gross_arr = np.array(ca["gross_bp"])
        ts_arr = np.array(ca["ts"])
        n = len(net_arr)
        # Aggregate t-stat
        obs_t = t_stat(net_arr)
        mean_net = float(np.mean(net_arr)) if n > 0 else 0.0
        mean_gross = float(np.mean(gross_arr)) if n > 0 else 0.0

        # Build candidate pool (union of all fwd_120m for fee-aware perm)
        pool = []
        for sym, df in per_sym.items():
            pool.extend(df[df["fwd_120m"].notna()]["fwd_120m"].values.tolist())
        pool = np.array(pool)
        # For non-LONG cells the sign is flipped — apply same sign convention to pool sample
        # But fee-aware perm uses observed_net + candidate_pool_returns; pool serves as raw fwd, so use abs/symmetric
        # Use raw pool directly: signal is whether observed mean exceeds random sampling from pool
        # For cells expressing -fwd (A_mirror, B_same), flip pool sign for parity
        if cell_name in ("A_mirror", "B_same"):
            pool_signed = -pool
        else:
            pool_signed = pool

        try:
            perm_res = fee_aware_perm_test(
                observed_net_returns=net_arr / 10000.0,           # bp → fraction
                candidate_pool_returns=pool_signed / 10000.0,     # bp → fraction
                fee_per_trade=FEE_PER_TRADE,
                n_perms=N_PERMS,
            )
        except Exception as e:
            log.error("perm test failed for %s: %s", cell_name, e)
            perm_res = {"obs_t": obs_t, "null_t_mean": None, "signal_t_excess": None, "perm_p": None}

        # Bootstrap CI (net bp)
        try:
            ci_res = bootstrap_ci(net_arr, n_boot=N_BOOT, block_size=20)
        except Exception as e:
            log.error("bootstrap failed for %s: %s", cell_name, e)
            ci_res = {"mean": mean_net, "ci_lower": None, "ci_upper": None, "prob_positive": None}

        # Concentration: per-sym CI
        per_sym_ci = {}
        n_ci_pos = 0
        for sym, arr_list in ca["per_sym"].items():
            arr = np.array(arr_list)
            if len(arr) < 30:
                per_sym_ci[sym] = {"n": len(arr), "ci_pos": None, "note": "n<30"}
                continue
            try:
                cires = bootstrap_ci(arr, n_boot=1000, block_size=10)
                ci_pos = bool(cires.get("ci_lower", -1) is not None and cires["ci_lower"] > 0)
                per_sym_ci[sym] = {"n": len(arr), "mean_bp": float(np.mean(arr)),
                                   "ci_lower_bp": float(cires["ci_lower"]) if cires["ci_lower"] is not None else None,
                                   "ci_upper_bp": float(cires["ci_upper"]) if cires["ci_upper"] is not None else None,
                                   "ci_pos": ci_pos}
                if ci_pos:
                    n_ci_pos += 1
            except Exception as e:
                per_sym_ci[sym] = {"n": len(arr), "error": str(e)}
        n_syms_measurable = sum(1 for v in per_sym_ci.values() if v.get("ci_pos") is not None)
        sym_ci_pos_ratio = n_ci_pos / n_syms_measurable if n_syms_measurable > 0 else 0.0

        # Per-quarter t
        df_q = pd.DataFrame({"net_bp": net_arr, "ts": pd.to_datetime(ts_arr)})
        df_q["quarter"] = df_q["ts"].apply(quarter_of)
        per_quarter_t = {}
        n_q_pos = 0
        n_q_measurable = 0
        for q, grp in df_q.groupby("quarter"):
            if len(grp) < 30:
                per_quarter_t[q] = {"n": len(grp), "t": None, "note": "n<30"}
                continue
            qt = t_stat(grp["net_bp"].values)
            per_quarter_t[q] = {"n": len(grp), "t": qt, "mean_bp": float(grp["net_bp"].mean())}
            n_q_measurable += 1
            if qt > 0:
                n_q_pos += 1
        q_pos_t_ratio = n_q_pos / n_q_measurable if n_q_measurable > 0 else 0.0

        # Per-era t (Item 6 alpha decay)
        df_q["era"] = df_q["ts"].apply(era_of)
        per_era = {}
        for era, grp in df_q.groupby("era"):
            if len(grp) < 30:
                per_era[era] = {"n": len(grp), "mean_bp": float(grp["net_bp"].mean()) if len(grp) > 0 else None, "t": None}
            else:
                per_era[era] = {"n": len(grp), "mean_bp": float(grp["net_bp"].mean()), "t": t_stat(grp["net_bp"].values)}

        cell_metric = {
            "n": n,
            "mean_gross_bp": mean_gross,
            "mean_net_bp": mean_net,
            "obs_t": obs_t,
            "null_t_mean": perm_res.get("null_t_mean"),
            "signal_t_excess": perm_res.get("signal_t_excess"),
            "perm_p": perm_res.get("perm_p"),
            "ci_lower_bp": ci_res.get("ci_lower"),
            "ci_upper_bp": ci_res.get("ci_upper"),
            "prob_positive": ci_res.get("prob_positive"),
            "per_quarter_t": per_quarter_t,
            "q_pos_t_ratio": q_pos_t_ratio,
            "n_q_measurable": n_q_measurable,
            "per_symbol_ci": per_sym_ci,
            "n_syms_ci_pos": n_ci_pos,
            "n_syms_measurable": n_syms_measurable,
            "sym_ci_pos_ratio": sym_ci_pos_ratio,
            "per_era": per_era,
        }
        # Three-gate verdict
        sigex = cell_metric["signal_t_excess"]
        ci_lo = cell_metric["ci_lower_bp"]
        ppv = cell_metric["perm_p"]
        gate_t = bool(sigex is not None and sigex >= SIGNAL_T_EXCESS_PASS)
        gate_ci = bool(ci_lo is not None and ci_lo > CI_LOWER_PASS_BP)
        gate_perm = bool(ppv is not None and ppv <= PERM_P_PASS)
        cell_metric["three_gate"] = {
            "signal_t_excess_pass": gate_t,
            "ci_lower_pass": gate_ci,
            "perm_p_pass": gate_perm,
            "all_three_pass": (gate_t and gate_ci and gate_perm),
        }
        # Concentration gate
        cg_q = q_pos_t_ratio >= QUARTER_POS_T_RATIO_PASS
        cg_s = sym_ci_pos_ratio >= SYMBOL_CI_POS_RATIO_PASS and n_ci_pos >= SYMBOL_CI_POS_N_PASS
        cell_metric["concentration_gate"] = {
            "quarter_pos_t_ratio_pass": cg_q,
            "symbol_ci_pos_pass": cg_s,
            "all_pass": (cg_q and cg_s),
        }
        metrics["cells"][cell_name] = cell_metric

        log.info("  %s  n=%d  gross=%+.2f net=%+.2f obs_t=%+.2f sigex=%s perm_p=%s ci_lo=%s",
                 cell_name, n, mean_gross, mean_net, obs_t,
                 f"{sigex:+.2f}" if sigex is not None else "NA",
                 f"{ppv:.3f}" if ppv is not None else "NA",
                 f"{ci_lo:+.2f}" if ci_lo is not None else "NA")
        log.info("    Concentration: q_pos_t_ratio=%.2f (%d/%d) sym_ci_pos=%d/%d ratio=%.2f",
                 q_pos_t_ratio, n_q_pos, n_q_measurable, n_ci_pos, n_syms_measurable, sym_ci_pos_ratio)

    # 3) Item 7 cross-set asymmetry check (Lesson #39 sub-class A explicit avoidance)
    Af = metrics["cells"]["A_focus"]["mean_net_bp"]
    Am = metrics["cells"]["A_mirror"]["mean_net_bp"]
    Bs = metrics["cells"]["B_same"]["mean_net_bp"]
    Bm = metrics["cells"]["B_mirror"]["mean_net_bp"]
    # Within-set tautology check (A_focus + A_mirror = -2*fee, B_same + B_mirror = -2*fee)
    fee_bp = FEE_PER_TRADE * 2 * 10000
    A_sum = Af + Am
    B_sum = Bs + Bm
    within_tautology = {
        "A_focus_plus_A_mirror_bp": A_sum,
        "expected_minus_2fee_bp": -2 * fee_bp,
        "A_within_tautology_pass": abs(A_sum - (-2 * fee_bp)) < 1.0,
        "B_same_plus_B_mirror_bp": B_sum,
        "B_within_tautology_pass": abs(B_sum - (-2 * fee_bp)) < 1.0,
    }
    # Cross-set asymmetry: |Af| vs |Bs| should differ if signal is real
    cross_set_asym = {
        "abs_A_focus_bp": abs(Af),
        "abs_B_same_bp": abs(Bs),
        "ratio": (max(abs(Af), abs(Bs)) / min(abs(Af), abs(Bs))) if min(abs(Af), abs(Bs)) > 0 else None,
        "asymmetric_pass_ratio_ge_1_5": (max(abs(Af), abs(Bs)) / min(abs(Af), abs(Bs))) >= 1.5 if min(abs(Af), abs(Bs)) > 0 else False,
    }
    metrics["item_7_snt_structural_integrity"] = {
        "within_set_tautology": within_tautology,
        "cross_set_asymmetry": cross_set_asym,
        "lesson_39_sub_class_a_avoidance": "PASS" if cross_set_asym["asymmetric_pass_ratio_ge_1_5"] else "FAIL_BROAD_UNIFORM_PATTERN_A_4TH_DOGFOOD",
    }

    # 4) Trigger temporal cluster analysis (lesson candidate post-206)
    # Group consecutive trigger bars (within ≤60min of each other = 1 episode)
    cluster_stats = {}
    for sym, df in per_sym.items():
        trig_ts = df[df["trigger"]].index.tolist()
        if not trig_ts: continue
        episodes = 1
        for i in range(1, len(trig_ts)):
            gap_min = (trig_ts[i] - trig_ts[i-1]).total_seconds() / 60.0
            if gap_min > 60:
                episodes += 1
        n_agg = len(trig_ts)
        ratio = episodes / n_agg if n_agg > 0 else None
        cluster_stats[sym] = {"n_aggregate": n_agg, "n_independent_episodes": episodes, "ratio": ratio}
    # Overall
    total_agg = sum(v["n_aggregate"] for v in cluster_stats.values())
    total_eps = sum(v["n_independent_episodes"] for v in cluster_stats.values())
    overall_ratio = total_eps / total_agg if total_agg > 0 else None
    metrics["trigger_temporal_cluster"] = {
        "per_sym": cluster_stats,
        "overall_n_aggregate": total_agg,
        "overall_n_independent_episodes": total_eps,
        "overall_ratio": overall_ratio,
        "cluster_risk": "HIGH" if overall_ratio is not None and overall_ratio < 0.5 else "LOW",
    }

    # 5) Hold sweep (+4h, +8h) re-compute for A_focus, B_same primary cells only
    hold_sweep = {}
    for hold in [240, 480]:
        sweep_cells = {c: {"net_bp": [], "gross_bp": []} for c in ["A_focus", "A_mirror", "B_same", "B_mirror"]}
        for sym, df in per_sym.items():
            cells_h, _ = build_quadrant_returns(df, hold)
            for cn, cd in cells_h.items():
                sweep_cells[cn]["net_bp"].extend(cd["net_bp"].tolist())
                sweep_cells[cn]["gross_bp"].extend(cd["gross_bp"].tolist())
        hold_sweep[f"hold_{hold}m"] = {}
        for cn, cd in sweep_cells.items():
            arr = np.array(cd["net_bp"])
            garr = np.array(cd["gross_bp"])
            hold_sweep[f"hold_{hold}m"][cn] = {
                "n": len(arr),
                "mean_gross_bp": float(garr.mean()) if len(garr) > 0 else None,
                "mean_net_bp": float(arr.mean()) if len(arr) > 0 else None,
                "obs_t": t_stat(arr),
            }
    metrics["hold_sweep"] = hold_sweep

    # 6) Overall R-1 verdict
    any_three_gate_pass = any(c["three_gate"]["all_three_pass"] for c in metrics["cells"].values())
    any_concentration_pass = any(c["concentration_gate"]["all_pass"] for c in metrics["cells"].values())
    pass_cells = [name for name, c in metrics["cells"].items() if c["three_gate"]["all_three_pass"]]
    pass_cells_full = [name for name, c in metrics["cells"].items()
                       if c["three_gate"]["all_three_pass"] and c["concentration_gate"]["all_pass"]]

    metrics["verdict"] = {
        "any_cell_three_gate_pass": any_three_gate_pass,
        "any_cell_concentration_pass": any_concentration_pass,
        "cells_three_gate_pass": pass_cells,
        "cells_three_gate_plus_concentration_pass": pass_cells_full,
        "summary": None,
    }
    if pass_cells_full:
        metrics["verdict"]["summary"] = f"PASS_R1_FULL cells={pass_cells_full}"
    elif pass_cells:
        metrics["verdict"]["summary"] = f"CONCENTRATED_R1_PASS cells={pass_cells} (concentration FAIL)"
    elif not any_three_gate_pass and metrics["item_7_snt_structural_integrity"]["lesson_39_sub_class_a_avoidance"] == "PASS":
        metrics["verdict"]["summary"] = "BROAD_FALSIFIED_ASYMMETRIC_NO_PASS_CELL"
    elif not any_three_gate_pass:
        metrics["verdict"]["summary"] = "BROAD_FALSIFIED_LESSON_39_SUB_CLASS_A"
    else:
        metrics["verdict"]["summary"] = "UNCLASSIFIED"

    log.info("=== R-1 OVERALL VERDICT: %s ===", metrics["verdict"]["summary"])
    log.info("Item 7 cross-set asymmetry: |A_focus|=%.2f vs |B_same|=%.2f ratio=%s avoidance=%s",
             cross_set_asym["abs_A_focus_bp"], cross_set_asym["abs_B_same_bp"],
             cross_set_asym["ratio"], metrics["item_7_snt_structural_integrity"]["lesson_39_sub_class_a_avoidance"])
    log.info("Temporal cluster overall ratio=%s (risk=%s)",
             overall_ratio, metrics["trigger_temporal_cluster"]["cluster_risk"])

    # 7) Save metrics
    out_path = OUT_DIR / "r1__metrics.json"
    with open(out_path, "w") as f:
        json.dump(metrics, f, indent=2, default=str)
    log.info("metrics written: %s", out_path)


if __name__ == "__main__":
    main()
