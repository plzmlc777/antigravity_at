"""Paradigm 179 R-1 stratify supplement — 2026Q1 reversal 본질 진단.

Focus cell: 8h B_same_sign (strongest in R-1).

Stratify dimensions:
1. pre-2026 aggregate (2024Q1–2025Q4, 8 quarters) vs 2026Q1 isolated
2. quarter-by-quarter breakdown (9 quarters): n / mean_bp / t / ci_lo / mean_perm_p
3. 2025Q4 + 2026Q1 sequential analysis (regime decay vs single outlier)
4. 14/14 syms quarter-by-quarter net-positive ratio drop check
5. (optional) WIF exclusion 13-sym aggregate
6. (optional) 7 deep-sym cohort (BTC/ETH/SOL/XRP/DOGE/BNB/LINK) narrowing

NOT a new paradigm dispatch. Counter does not increment. No R-2 advance.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research._perm_utils import bootstrap_ci, fee_aware_perm_test  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("p179_stratify")

PARADIGM = "paradigm179_intraday_count_concentration_max_4h_share_within_24h_z_directional_4h"
CACHE_DIR = ROOT / "runs/ohlcv_cache_12col"
OUT_DIR = ROOT / "runs/research_track" / PARADIGM
OUT_DIR.mkdir(parents=True, exist_ok=True)

SYMS_FULL = ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "BNB", "LINK", "LTC", "AVAX", "BCH", "FIL", "NEAR", "WIF"]
SYMS_DEEP7 = ["BTC", "ETH", "SOL", "XRP", "DOGE", "BNB", "LINK"]

WINDOW_BARS = 6
Z_WINDOW_BARS = 540
Z_THRESHOLD = 2.0
HOLD_BARS = 2  # 8h focus cell
FEE_PER_TRADE = 0.0008

# Focus quadrant
QUADRANT = "B_same_sign"  # max_share spike + max bar DOWN × SHORT continuation
QUAD_DIRECTION = -1.0  # SHORT


def load_symbol(sym: str) -> pd.DataFrame | None:
    fp = CACHE_DIR / f"{sym}USDT_4h.joblib"
    if not fp.exists():
        return None
    df = joblib.load(fp)
    if "count" not in df.columns or "close" not in df.columns:
        return None
    return df.sort_index()[["open", "high", "low", "close", "count"]].copy()


def compute_signals(df: pd.DataFrame) -> pd.DataFrame:
    cnt_vals = df["count"].astype(float).values
    n = len(cnt_vals)
    max_share = pd.Series(np.nan, index=df.index, dtype=float)
    max_offset = pd.Series(np.nan, index=df.index, dtype=float)
    for i in range(WINDOW_BARS - 1, n):
        w = cnt_vals[i - WINDOW_BARS + 1 : i + 1]
        s = w.sum()
        if s <= 0:
            continue
        max_share.iloc[i] = w.max() / s
        max_offset.iloc[i] = int(np.argmax(w))
    mean = max_share.rolling(Z_WINDOW_BARS, min_periods=Z_WINDOW_BARS).mean()
    std = max_share.rolling(Z_WINDOW_BARS, min_periods=Z_WINDOW_BARS).std()
    z = (max_share - mean) / std
    return pd.DataFrame({"close": df["close"].astype(float), "max_share": max_share, "max_offset": max_offset, "z": z})


def get_max_bar_direction(sigs: pd.DataFrame, df_raw: pd.DataFrame) -> pd.Series:
    direction = pd.Series(np.nan, index=sigs.index, dtype=float)
    opens = df_raw["open"].values
    closes = df_raw["close"].values
    offsets = sigs["max_offset"].values
    for i in range(len(sigs)):
        off = offsets[i]
        if np.isnan(off):
            continue
        idx = i - (WINDOW_BARS - 1) + int(off)
        if idx < 0:
            continue
        o, c = opens[idx], closes[idx]
        if o <= 0:
            continue
        direction.iloc[i] = 1.0 if c > o else (-1.0 if c < o else 0.0)
    return direction


def build_trades_for_quadrant(sigs: pd.DataFrame, direction_max: pd.Series, fwd_ret: pd.Series, quadrant: str) -> pd.DataFrame:
    df = pd.DataFrame({"z": sigs["z"], "dir_max": direction_max, "gross": fwd_ret}).dropna()
    df = df.loc[df["z"].abs() >= Z_THRESHOLD]
    if df.empty:
        return df.assign(direction=pd.Series(dtype=float), net=pd.Series(dtype=float))
    if quadrant == "B_same_sign":
        df = df.loc[df["dir_max"] < 0]
        direction = -1.0
    elif quadrant == "A_focus":
        df = df.loc[df["dir_max"] > 0]
        direction = 1.0
    else:
        raise ValueError(quadrant)
    if df.empty:
        return df.assign(direction=pd.Series(dtype=float), net=pd.Series(dtype=float))
    df = df.assign(direction=direction)
    df["net"] = df["direction"] * df["gross"] - FEE_PER_TRADE
    return df


def stratum_eval(net_arr: np.ndarray, label: str, pool_signed: np.ndarray | None = None, do_perm: bool = True) -> dict:
    """Evaluate a stratum: mean, t, bootstrap CI, optional fee-aware perm."""
    n = len(net_arr)
    if n < 5:
        return {"label": label, "n": int(n), "error": "n<5"}
    obs_mean = float(net_arr.mean())
    obs_std = float(net_arr.std(ddof=1))
    obs_t = obs_mean / obs_std * np.sqrt(n) if obs_std > 0 else 0.0
    ci = bootstrap_ci(net_arr, n_boot=2000, block_size=1)
    out = {
        "label": label,
        "n": int(n),
        "mean_bp": float(obs_mean * 10000),
        "obs_t": float(obs_t),
        "ci_lower_bp": float(ci["ci_lower"] * 10000),
        "ci_upper_bp": float(ci["ci_upper"] * 10000),
        "ci_prob_positive": float(ci["prob_positive"]),
        "ci_pos": bool(ci["ci_lower"] > 0),
    }
    if do_perm and pool_signed is not None and len(pool_signed) >= 100:
        perm = fee_aware_perm_test(
            observed_net_returns=net_arr,
            candidate_pool_returns=pool_signed,
            fee_per_trade=FEE_PER_TRADE,
            n_perms=1000,
            rng_seed=42,
        )
        out["null_mean_t"] = perm["null_mean_t"]
        out["signal_t_excess"] = perm["signal_t_excess"]
        out["perm_p_one_sided_above"] = perm["perm_p_one_sided_above"]
        out["three_gate_pass"] = bool(
            (not np.isnan(perm["signal_t_excess"])) and perm["signal_t_excess"] >= 2.0
            and ci["ci_lower"] > 0
            and (not np.isnan(perm["perm_p_one_sided_above"])) and perm["perm_p_one_sided_above"] <= 0.10
        )
    return out


def build_universe_trades(syms: list) -> tuple[pd.DataFrame, np.ndarray]:
    """Build the full trade table (entry_time, sym, gross, direction, net, quarter) +
    the signed candidate pool for fee-aware perm."""
    sym_signals = {}
    sym_directions = {}
    sym_raw = {}
    sym_fwd = {}
    for sym in syms:
        df = load_symbol(sym)
        if df is None:
            continue
        sigs = compute_signals(df)
        direction_max = get_max_bar_direction(sigs, df)
        fwd = df["close"].astype(float).shift(-HOLD_BARS) / df["close"].astype(float) - 1.0
        sym_signals[sym] = sigs
        sym_directions[sym] = direction_max
        sym_raw[sym] = df
        sym_fwd[sym] = fwd

    rows = []
    pool = []
    for sym in sym_signals:
        sigs = sym_signals[sym]
        fwd = sym_fwd[sym]
        # pool = all valid fwd returns where z is computable
        valid_idx = sigs["z"].dropna().index
        valid_fwd = fwd.reindex(valid_idx).dropna()
        pool.extend(valid_fwd.values.tolist())

        trades = build_trades_for_quadrant(sigs, sym_directions[sym], fwd, QUADRANT)
        if trades.empty:
            continue
        for ts, row in trades.iterrows():
            rows.append({
                "entry_time": ts,
                "sym": sym,
                "gross": float(row["gross"]),
                "direction": float(row["direction"]),
                "net": float(row["net"]),
            })
    if not rows:
        return pd.DataFrame(columns=["entry_time", "sym", "gross", "direction", "net", "quarter"]), np.asarray([])

    tdf = pd.DataFrame(rows)
    tdf["quarter"] = pd.to_datetime(tdf["entry_time"]).dt.to_period("Q").astype(str)
    pool_signed = np.asarray(pool, dtype=float) * QUAD_DIRECTION
    return tdf, pool_signed


def main():
    log.info("paradigm 179 stratify supplement — 8h B_same_sign focus, 2026Q1 reversal diagnostic")

    # === FULL 14-sym universe ===
    log.info("=== Building 14-sym full universe trades ===")
    full_trades, full_pool = build_universe_trades(SYMS_FULL)
    log.info("  total trades: %d", len(full_trades))
    log.info("  pool size: %d", len(full_pool))

    out = {
        "paradigm": PARADIGM,
        "phase": "R-1_stratify_supplement",
        "focus_cell": {"hold": "8h", "quadrant": QUADRANT, "z_threshold_abs": Z_THRESHOLD},
        "universe_full": [f"{s}USDT" for s in SYMS_FULL],
    }

    # 1. Pre-2026 (2024Q2–2025Q4) vs 2026Q1 isolated
    log.info("=== Stratum 1: pre-2026 vs 2026Q1 isolated ===")
    full_trades["entry_dt"] = pd.to_datetime(full_trades["entry_time"])
    pre2026 = full_trades[full_trades["entry_dt"] < pd.Timestamp("2026-01-01")]
    q1_2026 = full_trades[
        (full_trades["entry_dt"] >= pd.Timestamp("2026-01-01"))
        & (full_trades["entry_dt"] < pd.Timestamp("2026-04-01"))
    ]
    q2_2026 = full_trades[full_trades["entry_dt"] >= pd.Timestamp("2026-04-01")]

    pre_eval = stratum_eval(pre2026["net"].values, "pre_2026", full_pool, do_perm=True)
    q1_eval = stratum_eval(q1_2026["net"].values, "2026Q1", full_pool, do_perm=True)
    q2_eval = stratum_eval(q2_2026["net"].values, "2026Q2", full_pool, do_perm=True)

    out["stratum1_pre2026_vs_2026Q1"] = {
        "pre_2026": pre_eval,
        "2026Q1": q1_eval,
        "2026Q2": q2_eval,
    }
    log.info("  pre_2026: n=%d mean_bp=%.1f t=%.2f ci_lo=%.1f sigex=%s perm_p=%s",
             pre_eval.get("n", 0), pre_eval.get("mean_bp", 0), pre_eval.get("obs_t", 0),
             pre_eval.get("ci_lower_bp", 0), pre_eval.get("signal_t_excess", "n/a"),
             pre_eval.get("perm_p_one_sided_above", "n/a"))
    log.info("  2026Q1: n=%d mean_bp=%.1f t=%.2f ci_lo=%.1f sigex=%s perm_p=%s",
             q1_eval.get("n", 0), q1_eval.get("mean_bp", 0), q1_eval.get("obs_t", 0),
             q1_eval.get("ci_lower_bp", 0), q1_eval.get("signal_t_excess", "n/a"),
             q1_eval.get("perm_p_one_sided_above", "n/a"))

    # 2. Quarter-by-quarter breakdown (9 quarters)
    log.info("=== Stratum 2: quarter-by-quarter breakdown ===")
    qbreakdown = {}
    for q, sub in full_trades.groupby("quarter"):
        qbreakdown[q] = stratum_eval(sub["net"].values, q, full_pool, do_perm=False)
    # sort keys
    qbreakdown_sorted = {k: qbreakdown[k] for k in sorted(qbreakdown.keys())}
    out["stratum2_per_quarter"] = qbreakdown_sorted
    for q, ev in qbreakdown_sorted.items():
        log.info("  %s: n=%d mean_bp=%.1f t=%.2f ci_lo=%.1f ci_up=%.1f ci_pos=%s",
                 q, ev.get("n", 0), ev.get("mean_bp", 0), ev.get("obs_t", 0),
                 ev.get("ci_lower_bp", 0), ev.get("ci_upper_bp", 0), ev.get("ci_pos", False))

    # 3. 2025Q4 + 2026Q1 sequential analysis (regime-decay vs single-outlier)
    log.info("=== Stratum 3: 2025Q4 + 2026Q1 sequential analysis ===")
    q4_2025 = full_trades[full_trades["quarter"] == "2025Q4"]
    q1_full = full_trades[full_trades["quarter"] == "2026Q1"]

    # Split 2025Q4 into Oct+Nov vs Dec
    q4_2025_octnov = q4_2025[q4_2025["entry_dt"] < pd.Timestamp("2025-12-01")]
    q4_2025_dec = q4_2025[q4_2025["entry_dt"] >= pd.Timestamp("2025-12-01")]
    # Split 2026Q1 into Jan vs Feb+Mar
    q1_2026_jan = q1_full[q1_full["entry_dt"] < pd.Timestamp("2026-02-01")]
    q1_2026_febmar = q1_full[
        (q1_full["entry_dt"] >= pd.Timestamp("2026-02-01"))
        & (q1_full["entry_dt"] < pd.Timestamp("2026-04-01"))
    ]

    seq = {
        "2025Q4_OctNov": stratum_eval(q4_2025_octnov["net"].values, "2025Q4_OctNov", do_perm=False),
        "2025Q4_Dec": stratum_eval(q4_2025_dec["net"].values, "2025Q4_Dec", do_perm=False),
        "2026Q1_Jan": stratum_eval(q1_2026_jan["net"].values, "2026Q1_Jan", do_perm=False),
        "2026Q1_FebMar": stratum_eval(q1_2026_febmar["net"].values, "2026Q1_FebMar", do_perm=False),
    }
    out["stratum3_q4q1_sequential"] = seq
    for label, ev in seq.items():
        log.info("  %s: n=%d mean_bp=%.1f t=%.2f ci_lo=%.1f",
                 label, ev.get("n", 0), ev.get("mean_bp", 0), ev.get("obs_t", 0), ev.get("ci_lower_bp", 0))

    # 4. Per-sym quarterly net-positive ratio drop check
    log.info("=== Stratum 4: per-sym × quarter net-positive ratio ===")
    sym_q_table = {}
    for sym in SYMS_FULL:
        sym_q_table[sym] = {}
        sym_sub = full_trades[full_trades["sym"] == sym]
        for q, ssub in sym_sub.groupby("quarter"):
            n = len(ssub)
            mean = float(ssub["net"].mean()) if n > 0 else 0.0
            sym_q_table[sym][q] = {"n": int(n), "mean_bp": float(mean * 10000), "net_pos": bool(mean > 0)}
    out["stratum4_per_sym_per_quarter"] = sym_q_table

    # ratio of net-positive syms per quarter (only syms with n>=3)
    per_q_net_pos = {}
    all_quarters = sorted({q for sub in sym_q_table.values() for q in sub.keys()})
    for q in all_quarters:
        measurable = 0
        net_pos = 0
        for sym in SYMS_FULL:
            if q in sym_q_table[sym] and sym_q_table[sym][q]["n"] >= 3:
                measurable += 1
                if sym_q_table[sym][q]["net_pos"]:
                    net_pos += 1
        per_q_net_pos[q] = {
            "n_syms_measurable": measurable,
            "n_syms_net_pos": net_pos,
            "ratio": (net_pos / measurable) if measurable else 0.0,
        }
    out["stratum4_per_quarter_sym_net_pos_ratio"] = per_q_net_pos
    for q, ev in per_q_net_pos.items():
        log.info("  %s: %d/%d syms net-pos (%.1f%%)", q, ev["n_syms_net_pos"], ev["n_syms_measurable"], ev["ratio"] * 100)

    # === Optional: WIF exclusion 13-sym universe ===
    log.info("=== Optional: WIF exclusion 13-sym universe ===")
    syms_no_wif = [s for s in SYMS_FULL if s != "WIF"]
    no_wif_trades, no_wif_pool = build_universe_trades(syms_no_wif)
    no_wif_agg = stratum_eval(no_wif_trades["net"].values, "13_syms_no_WIF", no_wif_pool, do_perm=True)

    # syms with per-sym ci_pos in this universe
    no_wif_per_sym = {}
    for sym in syms_no_wif:
        sub = no_wif_trades[no_wif_trades["sym"] == sym]
        if len(sub) >= 5:
            ci = bootstrap_ci(sub["net"].values, n_boot=1000, block_size=1)
            no_wif_per_sym[sym] = {
                "n": int(len(sub)),
                "mean_bp": float(sub["net"].mean() * 10000),
                "ci_lower_bp": float(ci["ci_lower"] * 10000),
                "ci_pos": bool(ci["ci_lower"] > 0),
            }
    n_ci_pos_no_wif = sum(1 for v in no_wif_per_sym.values() if v["ci_pos"])
    n_measurable_no_wif = len(no_wif_per_sym)
    out["optional_wif_excluded_13sym"] = {
        "aggregate": no_wif_agg,
        "per_sym": no_wif_per_sym,
        "n_syms_measurable": n_measurable_no_wif,
        "n_syms_ci_pos": n_ci_pos_no_wif,
        "symbol_ci_pos_ratio": n_ci_pos_no_wif / n_measurable_no_wif if n_measurable_no_wif else 0.0,
    }
    log.info("  13-sym no-WIF aggregate: n=%d mean_bp=%.1f sigex=%s ci_lo=%.1f three_gate=%s",
             no_wif_agg.get("n", 0), no_wif_agg.get("mean_bp", 0), no_wif_agg.get("signal_t_excess", "n/a"),
             no_wif_agg.get("ci_lower_bp", 0), no_wif_agg.get("three_gate_pass", False))
    log.info("  13-sym no-WIF per-sym ci_pos: %d/%d (%.1f%%)",
             n_ci_pos_no_wif, n_measurable_no_wif, (n_ci_pos_no_wif / n_measurable_no_wif * 100) if n_measurable_no_wif else 0)

    # === Optional: 7 deep-sym cohort ===
    log.info("=== Optional: 7 deep-sym cohort (BTC/ETH/SOL/XRP/DOGE/BNB/LINK) ===")
    deep_trades, deep_pool = build_universe_trades(SYMS_DEEP7)
    deep_agg = stratum_eval(deep_trades["net"].values, "7_deep_syms", deep_pool, do_perm=True)
    deep_per_sym = {}
    for sym in SYMS_DEEP7:
        sub = deep_trades[deep_trades["sym"] == sym]
        if len(sub) >= 5:
            ci = bootstrap_ci(sub["net"].values, n_boot=1000, block_size=1)
            deep_per_sym[sym] = {
                "n": int(len(sub)),
                "mean_bp": float(sub["net"].mean() * 10000),
                "ci_lower_bp": float(ci["ci_lower"] * 10000),
                "ci_pos": bool(ci["ci_lower"] > 0),
            }
    n_ci_pos_deep = sum(1 for v in deep_per_sym.values() if v["ci_pos"])
    n_measurable_deep = len(deep_per_sym)
    out["optional_deep7_cohort"] = {
        "aggregate": deep_agg,
        "per_sym": deep_per_sym,
        "n_syms_measurable": n_measurable_deep,
        "n_syms_ci_pos": n_ci_pos_deep,
        "symbol_ci_pos_ratio": n_ci_pos_deep / n_measurable_deep if n_measurable_deep else 0.0,
    }
    log.info("  7-deep aggregate: n=%d mean_bp=%.1f sigex=%s ci_lo=%.1f three_gate=%s",
             deep_agg.get("n", 0), deep_agg.get("mean_bp", 0), deep_agg.get("signal_t_excess", "n/a"),
             deep_agg.get("ci_lower_bp", 0), deep_agg.get("three_gate_pass", False))
    log.info("  7-deep per-sym ci_pos: %d/%d (%.1f%%)",
             n_ci_pos_deep, n_measurable_deep, (n_ci_pos_deep / n_measurable_deep * 100) if n_measurable_deep else 0)

    # also pre-2026 only for deep7
    deep_trades["entry_dt"] = pd.to_datetime(deep_trades["entry_time"])
    deep_pre2026 = deep_trades[deep_trades["entry_dt"] < pd.Timestamp("2026-01-01")]
    deep_pre_eval = stratum_eval(deep_pre2026["net"].values, "7_deep_pre2026", deep_pool, do_perm=True)
    out["optional_deep7_pre2026"] = deep_pre_eval
    log.info("  7-deep pre-2026: n=%d mean_bp=%.1f sigex=%s ci_lo=%.1f three_gate=%s",
             deep_pre_eval.get("n", 0), deep_pre_eval.get("mean_bp", 0),
             deep_pre_eval.get("signal_t_excess", "n/a"), deep_pre_eval.get("ci_lower_bp", 0),
             deep_pre_eval.get("three_gate_pass", False))

    # === CASE A/B/C verdict ===
    # CASE A: pre-2026 PASS + 2026Q1 isolated outlier (regime continues post-Q1 or single quarter)
    # CASE B: 2025Q4 + 2026Q1 both reversal -> regime-decay
    # CASE C: pre-2026 heterogeneous (many quarters poor)
    pre_pass = pre_eval.get("three_gate_pass", False)
    q4_t = qbreakdown_sorted.get("2025Q4", {}).get("obs_t", 0)
    q1_t = qbreakdown_sorted.get("2026Q1", {}).get("obs_t", 0)
    pos_q_count = sum(1 for ev in qbreakdown_sorted.values() if ev.get("obs_t", 0) > 0 and ev.get("n", 0) >= 5)
    n_q_measurable = sum(1 for ev in qbreakdown_sorted.values() if ev.get("n", 0) >= 5)
    pos_ratio = pos_q_count / n_q_measurable if n_q_measurable else 0.0

    if pre_pass and q4_t > 2 and q1_t < 0:
        case_verdict = "CASE_A_2026Q1_ISOLATED_OUTLIER"
        case_reason = (
            f"pre-2026 three-gate PASS, 2025Q4 t={q4_t:.2f} strong continuation, "
            f"2026Q1 t={q1_t:.2f} isolated reversal. R-2 wf 진입 정당, life-changing paradigm candidate."
        )
    elif q4_t < 1.0 and q1_t < 0:
        case_verdict = "CASE_B_REGIME_DECAY"
        case_reason = (
            f"2025Q4 t={q4_t:.2f} weak + 2026Q1 t={q1_t:.2f} negative — regime-decay. "
            "R-2 진입 보류 + spec adjustment 권고."
        )
    elif pos_ratio < 0.6:
        case_verdict = "CASE_C_PRE2026_HETEROGENEOUS"
        case_reason = (
            f"pre-2026 quarter pos ratio {pos_ratio:.2f} < 0.6 — heterogeneous. "
            "R-2 wf 진입 risk, 추가 supplement 측정 필요."
        )
    else:
        case_verdict = "MIXED_INCONCLUSIVE"
        case_reason = (
            f"pre-2026 three-gate PASS={pre_pass}, q4_t={q4_t:.2f}, q1_t={q1_t:.2f}, "
            f"pos_ratio={pos_ratio:.2f}. 명확한 case 분류 안 됨."
        )

    out["case_verdict"] = {
        "verdict": case_verdict,
        "reason": case_reason,
        "pre_2026_three_gate_pass": pre_pass,
        "2025Q4_t": float(q4_t),
        "2026Q1_t": float(q1_t),
        "pre_2026_pos_quarter_ratio": float(pos_ratio),
    }
    log.info("=== CASE VERDICT: %s ===", case_verdict)
    log.info("    %s", case_reason)

    # R-2 recommendation
    if case_verdict == "CASE_A_2026Q1_ISOLATED_OUTLIER":
        r2_rec = "PROCEED — R-2 walk-forward 진입 권고 (2026Q1 OOS fold 포함하여 robustness 검증)"
    elif case_verdict == "CASE_B_REGIME_DECAY":
        r2_rec = "HOLD — R-2 진입 보류, spec adjustment 권고 (z_threshold 재조정 / hold 길이 / sub-regime filter)"
    elif case_verdict == "CASE_C_PRE2026_HETEROGENEOUS":
        r2_rec = "SPEC_ADJUST — pre-2026 sub-period stratify 후 R-2 진입 검토"
    else:
        r2_rec = "INCONCLUSIVE — 추가 진단 필요"
    out["r2_recommendation"] = r2_rec
    log.info("=== R-2 RECOMMENDATION: %s ===", r2_rec)

    out_fp = OUT_DIR / "r1__stratify_supplement.json"
    with open(out_fp, "w") as fh:
        json.dump(out, fh, indent=2, default=str)
    log.info("wrote %s", out_fp)


if __name__ == "__main__":
    main()
