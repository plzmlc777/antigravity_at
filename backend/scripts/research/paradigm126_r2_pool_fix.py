"""paradigm 126 R-2 pool-fix patch.

Bug in initial R-2 (paradigm126_r2_walk_forward.py): candidate_pool_bp was sampled
from primary_panel.gross_bp (trigger-only events, n=28k, mean ~+70bp). This caused
fee_aware_perm_test to operate on a positively-biased pool, severely degrading the
signal_t_excess (arm A from R-1's +50.33 to R-2's +10.58; arm B NaN early-return
because |negated pool| < 2× |obs|).

Fix: pool should be unconditional fwd_ret_30m of ALL 5m bars (~2.77M), matching the
R-1 construction. This re-computes ONLY the primary R-2 stats + broad-shoulders
top-3 exclusion using the corrected pool, and patches r2__metrics.json in-place.

All other phases (TS-CV, threshold sweep, slippage stress, hold horizon sweep,
life-changing 4-dim) are not pool-dependent and remain as-computed.
"""
from __future__ import annotations

import json
import logging
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

ROOT = Path("/home/hcpark/antigravity/backend")
sys.path.insert(0, str(ROOT))

from scripts.research._perm_utils import fee_aware_perm_test, bootstrap_ci  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("p126_r2_pool_fix")

PARADIGM_NAME = "alt_volume_burst_intra5m_event_signed_directional_30m"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_NAME

COHORT = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT",
    "SOLUSDT", "WIFUSDT", "XRPUSDT",
]
ROLLING_BAR_WINDOW = 30 * 24 * 60
PRIMARY_PCTILE = 99.0
PRIMARY_MAG = 0.005
PRIMARY_HOLD_MIN = 30
PRIMARY_FEE_BP = 16.0
DB_DSN = "postgresql://antigravity_user:antigravity_password@localhost:5432/antigravity_db"


def load_ohlcv_1m(sym: str, engine) -> pd.DataFrame:
    q = text(
        "SELECT timestamp, open, high, low, close, volume FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
    )
    df = pd.read_sql(q, engine, params={"s": sym}, parse_dates=["timestamp"])
    if df.empty:
        return df
    return df.set_index("timestamp")


def _t_stat(arr) -> float:
    arr = np.asarray(arr, dtype=float)
    n = len(arr)
    if n < 2:
        return 0.0
    sd = arr.std(ddof=1)
    if sd == 0 or not np.isfinite(sd):
        return 0.0
    return float(arr.mean() / sd * math.sqrt(n))


def _convert(obj):
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        f = float(obj)
        if np.isnan(f) or np.isinf(f):
            return None
        return f
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _convert(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_convert(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    return obj


def build_panel_and_pool(sym_data: dict) -> tuple[pd.DataFrame, np.ndarray]:
    """Build trigger panel AND retain full 5m fwd_ret panel for pool.

    Returns (trigger_panel, full_5m_fwd_ret_bp).
    """
    rows = []
    pool_pieces = []
    for sym, df in sym_data.items():
        j = df.copy()
        j["log_ret_1m"] = np.log(j["close"]).diff()
        j["abs_log_ret_1m"] = j["log_ret_1m"].abs()
        j["vol_pctile_30d"] = (
            j["volume"].rolling(
                window=ROLLING_BAR_WINDOW, min_periods=ROLLING_BAR_WINDOW // 2
            ).quantile(PRIMARY_PCTILE / 100.0)
        )
        j["burst"] = (
            (j["volume"] > j["vol_pctile_30d"])
            & (j["abs_log_ret_1m"] > PRIMARY_MAG)
        ).astype(int)
        j["burst_sign"] = np.where(
            j["burst"] == 1, np.sign(j["log_ret_1m"]), 0
        ).astype(int)
        j["fwd_ret"] = j["close"].pct_change(PRIMARY_HOLD_MIN).shift(-PRIMARY_HOLD_MIN)

        first_sign_func = lambda x: int(x[x != 0].iloc[0]) if (x != 0).any() else 0
        j_5m = j.resample("5min").agg({
            "burst": "max",
            "burst_sign": first_sign_func,
            "fwd_ret": "first",
        })
        j_5m = j_5m.dropna(subset=["fwd_ret"])
        # full 5m pool (gross fwd_ret in bp)
        pool_pieces.append(j_5m["fwd_ret"].values * 10000.0)
        # trigger panel
        trig = j_5m[j_5m["burst"] == 1].copy()
        if trig.empty:
            continue
        trig["sym"] = sym
        trig["direction"] = trig["burst_sign"].astype(int)
        trig["gross_bp"] = trig["fwd_ret"] * trig["direction"] * 10000.0
        trig["qtr"] = trig.index.to_period("Q").astype(str)
        rows.append(trig.reset_index().rename(columns={"timestamp": "ts", "index": "ts"}))
    if not rows:
        return pd.DataFrame(), np.array([])
    panel = pd.concat(rows, ignore_index=True)
    if "ts" not in panel.columns:
        panel.rename(columns={panel.columns[0]: "ts"}, inplace=True)
    panel = panel.sort_values("ts").reset_index(drop=True)
    full_pool = np.concatenate(pool_pieces) if pool_pieces else np.array([])
    return panel[["ts", "sym", "direction", "gross_bp", "qtr"]], full_pool


def evaluate_cell_v2(
    panel: pd.DataFrame,
    arm: str,
    fee_bp: float,
    candidate_pool_unconditional_bp: np.ndarray,
) -> dict:
    """Evaluate one arm, using unconditional 5m fwd_ret pool (corrected)."""
    if arm == "A":
        sub = panel[panel["direction"] > 0]
        pool_for_arm = candidate_pool_unconditional_bp  # positive direction → match
    else:
        sub = panel[panel["direction"] < 0]
        pool_for_arm = -candidate_pool_unconditional_bp  # negate for SHORT
    if len(sub) < 30:
        return {"arm": arm, "n": int(len(sub)), "skip": True}
    gross = sub["gross_bp"].values
    net = gross - fee_bp
    obs_t = _t_stat(net)
    ci = bootstrap_ci(net / 10000.0, n_boot=2000, block_size=20, rng_seed=42)
    perm = fee_aware_perm_test(
        observed_net_returns=net / 10000.0,
        candidate_pool_returns=pool_for_arm / 10000.0,
        fee_per_trade=fee_bp / 10000.0,
        n_perms=1000,
        rng_seed=42,
    )

    # per-quarter t
    q_t_map = {}
    for q in sub["qtr"].unique():
        s = sub[sub["qtr"] == q]
        if len(s) >= 30:
            q_t_map[q] = _t_stat(s["gross_bp"].values - fee_bp)
    n_q = len(q_t_map)
    n_q_pos = sum(1 for t in q_t_map.values() if t > 0)

    # per-symbol ci_pos
    n_sym_ci_pos = 0
    n_sym_meas = 0
    sym_ranking = []
    for s in sub["sym"].unique():
        ss = sub[sub["sym"] == s]
        if len(ss) >= 30:
            n_sym_meas += 1
            sym_net = ss["gross_bp"].values - fee_bp
            sym_ci = bootstrap_ci(sym_net / 10000.0, n_boot=500, block_size=10, rng_seed=42)
            sym_lb = float(sym_ci["ci_lower"]) * 10000
            sym_ranking.append({
                "sym": s, "n": int(len(ss)),
                "gross_bp": float(ss["gross_bp"].mean()),
                "net_bp": float(sym_net.mean()),
                "ci_lower_bp": sym_lb, "ci_pos": bool(sym_lb > 0),
            })
            if sym_lb > 0:
                n_sym_ci_pos += 1

    return {
        "arm": arm,
        "n": int(len(sub)),
        "gross_bp": float(gross.mean()),
        "net_bp": float(net.mean()),
        "obs_t": obs_t,
        "signal_t_excess": float(perm.get("signal_t_excess", float("nan"))),
        "null_mean_t": float(perm.get("null_mean_t", float("nan"))),
        "perm_p_one_sided_above": float(perm.get("perm_p_one_sided_above", float("nan"))),
        "perm_p_two_sided": float(perm.get("perm_p_two_sided", float("nan"))),
        "ci_lower_bp": float(ci["ci_lower"]) * 10000,
        "ci_upper_bp": float(ci["ci_upper"]) * 10000,
        "n_q_measurable": n_q,
        "n_q_pos_t": n_q_pos,
        "q_pos_t_ratio": n_q_pos / n_q if n_q else 0.0,
        "per_quarter_t": q_t_map,
        "n_syms_measurable": n_sym_meas,
        "n_syms_ci_pos": n_sym_ci_pos,
        "syms_ci_pos_ratio": n_sym_ci_pos / n_sym_meas if n_sym_meas else 0.0,
        "per_symbol": sym_ranking,
    }


def main():
    t_start = time.time()
    log.info("paradigm 126 R-2 pool-fix start")
    engine = create_engine(DB_DSN)

    # Phase 1: load 1m OHLCV
    log.info("=" * 70)
    log.info("PHASE 1: load 1m OHLCV per symbol")
    log.info("=" * 70)
    sym_data = {}
    for sym in COHORT:
        try:
            df = load_ohlcv_1m(sym, engine)
            if df.empty or len(df) < ROLLING_BAR_WINDOW * 2:
                continue
            sym_data[sym] = df
            log.info("  %s: %d 1m bars", sym, len(df))
        except Exception as e:
            log.error("  %s load fail: %s", sym, e)

    if len(sym_data) < 8:
        log.error("insufficient symbols")
        return 1

    # Phase 2: build panel + full pool
    log.info("=" * 70)
    log.info("PHASE 2: build trigger panel + UNCONDITIONAL 5m fwd_ret pool")
    log.info("=" * 70)
    panel, full_pool_bp = build_panel_and_pool(sym_data)
    log.info("trigger panel: %d events", len(panel))
    log.info("full unconditional 5m pool: %d bars (mean=%.4f bp std=%.2f bp)",
             len(full_pool_bp), float(full_pool_bp.mean()), float(full_pool_bp.std()))

    # subsample pool to 50k (consistent with R-1)
    rng = np.random.default_rng(126)
    if len(full_pool_bp) > 50000:
        idx = rng.choice(len(full_pool_bp), size=50000, replace=False)
        pool_50k = full_pool_bp[idx]
    else:
        pool_50k = full_pool_bp
    log.info("subsampled pool to %d bars (mean=%.4f bp)", len(pool_50k), float(pool_50k.mean()))

    # Phase 3: primary R-2 per arm with corrected pool
    log.info("=" * 70)
    log.info("PHASE 3: Primary R-2 per-arm (CORRECTED unconditional pool)")
    log.info("=" * 70)
    arms_primary = {}
    for arm in ["A", "B"]:
        res = evaluate_cell_v2(panel, arm, PRIMARY_FEE_BP, pool_50k)
        arms_primary[arm] = res
        log.info("  arm=%s n=%d gross=%.2fbp net=%.2fbp obs_t=%.2f sigex=%.2f "
                 "ci[%.2f,%.2f] perm_p_above=%.3f q_pos=%d/%d sym_ci_pos=%d/%d",
                 arm, res["n"], res["gross_bp"], res["net_bp"], res["obs_t"],
                 res["signal_t_excess"], res["ci_lower_bp"], res["ci_upper_bp"],
                 res["perm_p_one_sided_above"], res["n_q_pos_t"], res["n_q_measurable"],
                 res["n_syms_ci_pos"], res["n_syms_measurable"])

    # Phase 4: broad shoulders top-3 exclusion (CORRECTED pool)
    log.info("=" * 70)
    log.info("PHASE 4: broad-shoulders top-3 exclusion (CORRECTED pool)")
    log.info("=" * 70)
    broad_shoulders = {}
    for arm in ["A", "B"]:
        primary = arms_primary[arm]
        per_sym = primary["per_symbol"]
        ranked = sorted(per_sym, key=lambda x: -x["gross_bp"])
        top3_syms = [r["sym"] for r in ranked[:3]]
        if arm == "A":
            sub_excl = panel[(panel["direction"] > 0) & (~panel["sym"].isin(top3_syms))]
            pool_for_arm = pool_50k
        else:
            sub_excl = panel[(panel["direction"] < 0) & (~panel["sym"].isin(top3_syms))]
            pool_for_arm = -pool_50k
        if len(sub_excl) < 30:
            broad_shoulders[arm] = {"top3_syms": top3_syms, "skip": True}
            continue
        gross = sub_excl["gross_bp"].values
        net = gross - PRIMARY_FEE_BP
        obs_t = _t_stat(net)
        ci = bootstrap_ci(net / 10000.0, n_boot=2000, block_size=20, rng_seed=42)
        perm = fee_aware_perm_test(
            observed_net_returns=net / 10000.0,
            candidate_pool_returns=pool_for_arm / 10000.0,
            fee_per_trade=PRIMARY_FEE_BP / 10000.0,
            n_perms=1000, rng_seed=42,
        )
        sigex = float(perm.get("signal_t_excess", float("nan")))
        r1_sigex = 50.33 if arm == "A" else 37.59
        ci_lower_bp = float(ci["ci_lower"]) * 10000
        broad_shoulders[arm] = {
            "top3_syms_removed": top3_syms,
            "top3_per_sym_gross_bp": {r["sym"]: r["gross_bp"] for r in ranked[:3]},
            "n_residual": int(len(sub_excl)),
            "gross_bp_residual": float(gross.mean()),
            "net_bp_residual": float(net.mean()),
            "obs_t_residual": obs_t,
            "signal_t_excess_residual": sigex,
            "perm_p_one_sided_above_residual": float(perm.get("perm_p_one_sided_above", float("nan"))),
            "ci_lower_bp_residual": ci_lower_bp,
            "ci_upper_bp_residual": float(ci["ci_upper"]) * 10000,
            "r1_sigex_reference": r1_sigex,
            "sigex_80pct_threshold": 0.80 * r1_sigex,
            "broad_shoulders_pass_sigex": bool(sigex >= 0.80 * r1_sigex),
            "broad_shoulders_pass_ci_lower": bool(ci_lower_bp > 0),
            "broad_shoulders_pass": bool(sigex >= 0.80 * r1_sigex and ci_lower_bp > 0),
        }
        log.info("  arm=%s top3=%s n_residual=%d gross=%.2fbp sigex=%.2f (≥%.2f?) ci_lower=%.2f pass=%s",
                 arm, top3_syms, len(sub_excl), float(gross.mean()), sigex,
                 0.80 * r1_sigex, ci_lower_bp, broad_shoulders[arm]["broad_shoulders_pass"])

    # Patch r2__metrics.json
    log.info("=" * 70)
    log.info("PHASE 5: patch r2__metrics.json")
    log.info("=" * 70)
    metrics_path = OUT_DIR / "r2__metrics.json"
    with open(metrics_path) as f:
        out = json.load(f)
    out["primary_r2_per_arm"] = arms_primary
    out["broad_shoulders_top3_exclusion"] = broad_shoulders
    out["pool_fix_applied"] = {
        "fix_timestamp_kst": pd.Timestamp.now(tz="Asia/Seoul").isoformat(),
        "bug": "primary_r2 + broad_shoulders pool was triggers-only (biased +70bp mean); fee_aware_perm_test early-return for arm B",
        "fix": "use unconditional 5m fwd_ret panel pool (matches R-1 construction)",
        "pool_size": int(len(pool_50k)),
        "pool_mean_bp": float(pool_50k.mean()),
        "pool_std_bp": float(pool_50k.std()),
    }

    # Re-run verdict with corrected primary stats
    arm_verdicts = {}
    ts_cv = out["ts_cv_5fold"]
    lc4 = out["life_changing_4dim_dual_mode"]
    pctile_mono = out["pctile_monotone_check"]
    hold_mono = out["hold_horizon_monotone_check"]
    for arm in ["A", "B"]:
        primary = arms_primary[arm]
        flags = {
            "primary_3gate_pass": bool(
                primary["signal_t_excess"] >= 2.0
                and primary["ci_lower_bp"] > 0
                and primary["perm_p_one_sided_above"] <= 0.10
            ),
            "ts_cv_pass": ts_cv.get(f"{arm}_ts_cv_pass", False),
            "broad_shoulders_pass": broad_shoulders[arm].get("broad_shoulders_pass", False),
            "slippage_high_freq_30pct_pass": bool(
                lc4[arm].get("pass_high_freq_diffuse_mode_ann_gross_30_post_slippage", False)
            ),
            "hold_horizon_30_local_max": (
                hold_mono[arm].get("30min_local_max_in_ann_gross", False)
                if not hold_mono[arm].get("insufficient") else False
            ),
            "pctile_tpy_monotone_inc": (
                pctile_mono[arm].get("tpy_monotone_increase", False)
                if not pctile_mono[arm].get("insufficient") else False
            ),
        }
        if not flags["primary_3gate_pass"]:
            v = "FAIL_PRIMARY_3GATE"
        elif not flags["ts_cv_pass"]:
            v = "FRAGILE_TS_CV_FAIL"
        elif not flags["broad_shoulders_pass"]:
            v = "NARROW_UNIVERSE_FAIL"
        elif not flags["slippage_high_freq_30pct_pass"]:
            v = "SLIPPAGE_FAIL"
        else:
            v = "PASS_R2_HIGH_FREQ_DIFFUSE"
        arm_verdicts[arm] = {"flags": flags, "verdict": v}
        log.info("  arm=%s verdict=%s flags=%s", arm, v, flags)

    if any(v["verdict"] == "PASS_R2_HIGH_FREQ_DIFFUSE" for v in arm_verdicts.values()):
        final_verdict = "PASS_R2_HIGH_FREQ_DIFFUSE"
    else:
        failure_ranking = [
            "FAIL_PRIMARY_3GATE", "FRAGILE_TS_CV_FAIL",
            "NARROW_UNIVERSE_FAIL", "SLIPPAGE_FAIL",
        ]
        seen = [v["verdict"] for v in arm_verdicts.values()]
        final_verdict = "UNDETERMINED"
        for f in failure_ranking:
            if f in seen:
                final_verdict = f
                break
    out["arm_verdicts"] = arm_verdicts
    out["verdict"] = final_verdict
    out["pool_fix_wall_clock_min"] = (time.time() - t_start) / 60

    with open(metrics_path, "w") as f:
        json.dump(_convert(out), f, indent=2)
    log.info("FINAL CORRECTED VERDICT: %s", final_verdict)
    log.info("Wall-clock: %.1f min", (time.time() - t_start) / 60)
    log.info("metrics patched: %s", metrics_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
