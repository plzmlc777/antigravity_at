"""paradigm 121 R-0 prescreen — hmm_realized_vol_state_x_markprice_basis_extreme_alt_directional_4h

R-0 prescreen ONLY (Lesson #11, #28, #34, #46-candidate). Do NOT run R-1 from this script.

Mechanism
---------
- Per-symbol 3-state Gaussian HMM × 1h log-returns (weekly walk-forward refit, posterior >=0.8)
- External orthogonal axis: markPrice basis 1h z-score (|z|>2)
- 4-quadrant SNT — A_focus HIGH-vol × basis z>+2 × SHORT 4h, etc.

Prescreens
----------
(P1) Substrate availability — markPrice + indexPrice archive 1h aggregate, microstructure joblib
(P2) Lesson #11 sample density — empirical |basis z|>2 rate × HIGH vol state freq × cohort × window
(P3) Lesson #34 empirical distribution — basis_pct p50/p90/p99/max, |z| dist
(P4) Lesson #46 candidate — small sample (n~200) gross drift estimate vs 16bp fee floor
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("paradigm121_r0")

PARADIGM_NAME = "hmm_realized_vol_state_x_markprice_basis_extreme_alt_directional_4h"
OUTPUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_NAME
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Universe — use paradigm 105 cache subset (6 alts available locally)
# Note: full 13-alt paradigm 119 universe would require additional archive fetch
ALTS_CACHED = ["SOLUSDT", "HBARUSDT", "AVAXUSDT", "DOGEUSDT", "ETHUSDT", "LINKUSDT"]
ALTS_FULL = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT", "ETHUSDT",
    "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

MARK_INDEX_CACHE = ROOT / "runs" / "research_track" / "binance_perp_mark_index_basis_extreme_alt_directional_4h" / "mark_index_cache"
MICRO_CACHE = ROOT / "runs" / "microstructure"

FEE_PER_TRADE_BP = 8.0
FEE_FLOOR_BP = 16.0  # round-trip = 2x

# Frame: 1h basis (aggregated from 5m) × 4h hold (= 4 1h bars)
ROLLING_WIN_1H = 24 * 30  # 30 days for z-score (per request)
HOLD_BARS_1H = 4


def load_mark_index_5m(sym: str) -> tuple[pd.Series | None, pd.Series | None]:
    """Load monthly markPriceKlines + indexPriceKlines from paradigm 105 cache, concat."""
    mark_files = sorted(MARK_INDEX_CACHE.glob(f"{sym}_markPriceKlines_*.joblib"))
    index_files = sorted(MARK_INDEX_CACHE.glob(f"{sym}_indexPriceKlines_*.joblib"))
    if not mark_files or not index_files:
        return None, None

    def load_concat(files: list[Path]) -> pd.Series:
        dfs = []
        for f in files:
            try:
                obj = joblib.load(f)
                if isinstance(obj, pd.DataFrame):
                    if "close" in obj.columns:
                        dfs.append(obj["close"])
                    else:
                        # Try first numeric col
                        num = obj.select_dtypes(include=[np.number])
                        if not num.empty:
                            dfs.append(num.iloc[:, 0])
                elif isinstance(obj, pd.Series):
                    dfs.append(obj)
            except Exception as e:
                log.warning(f"load fail {f.name}: {e}")
        if not dfs:
            return None
        s = pd.concat(dfs).sort_index()
        # dedup index
        s = s[~s.index.duplicated(keep="first")]
        return s

    mark = load_concat(mark_files)
    index = load_concat(index_files)
    return mark, index


def aggregate_1h(s: pd.Series) -> pd.Series:
    """Aggregate 5m series → 1h close (last value per hour bucket)."""
    if s is None or len(s) == 0:
        return None
    return s.resample("1h").last().dropna()


def main() -> int:
    t0 = time.time()
    log.info(f"paradigm 121 R-0 prescreen — {PARADIGM_NAME}")

    out: dict = {
        "paradigm_name": PARADIGM_NAME,
        "paradigm_id_candidate": 121,
        "prescreen_only": True,
        "substrate_inventory": {},
        "lesson_34_empirical_distribution": {},
        "lesson_11_sample_density": {},
        "lesson_46_gross_drift_estimate": {},
        "verdict": None,
    }

    # P1: Substrate availability — paradigm 105 cache subset
    avail_syms: list[str] = []
    for sym in ALTS_CACHED:
        mark5, index5 = load_mark_index_5m(sym)
        if mark5 is None or index5 is None or len(mark5) < 1000 or len(index5) < 1000:
            log.warning(f"{sym}: substrate UNAVAILABLE in local cache")
            out["substrate_inventory"][sym] = {"available": False}
            continue
        m1h = aggregate_1h(mark5)
        i1h = aggregate_1h(index5)
        if m1h is None or i1h is None or len(m1h) < 100:
            log.warning(f"{sym}: 1h aggregation FAIL")
            out["substrate_inventory"][sym] = {"available": False, "reason": "agg_fail"}
            continue
        out["substrate_inventory"][sym] = {
            "available": True,
            "mark_5m_rows": int(len(mark5)),
            "index_5m_rows": int(len(index5)),
            "mark_1h_rows": int(len(m1h)),
            "date_range": [str(m1h.index.min()), str(m1h.index.max())],
        }
        avail_syms.append(sym)
        log.info(f"  {sym}: 1h rows={len(m1h)}, range={m1h.index.min()} ~ {m1h.index.max()}")

    if len(avail_syms) < 4:
        log.error("Substrate unavailable for >= 4 alts — HALT R-0")
        out["verdict"] = "DISPATCH_IMPOSSIBLE_SUBSTRATE_UNAVAILABLE"
        with open(OUTPUT_DIR / "r0_prescreen.json", "w") as f:
            json.dump(out, f, indent=2, default=str)
        return 2

    log.info(f"Substrate available: {len(avail_syms)} alts {avail_syms}")

    # P2/P3: Build basis 1h series for each available sym + empirical distribution
    sym_data: dict[str, pd.DataFrame] = {}
    all_basis_pct = []
    all_basis_z = []

    for sym in avail_syms:
        mark5, index5 = load_mark_index_5m(sym)
        m1h = aggregate_1h(mark5)
        i1h = aggregate_1h(index5)
        df = pd.DataFrame({"mark": m1h, "index": i1h}).dropna()
        df["basis_pct"] = (df["mark"] - df["index"]) / df["index"]
        # Rolling 30d z-score
        df["basis_mu"] = df["basis_pct"].rolling(ROLLING_WIN_1H, min_periods=ROLLING_WIN_1H // 2).mean()
        df["basis_sd"] = df["basis_pct"].rolling(ROLLING_WIN_1H, min_periods=ROLLING_WIN_1H // 2).std()
        df["basis_z"] = (df["basis_pct"] - df["basis_mu"]) / df["basis_sd"].replace(0, np.nan)
        df["basis_z"] = df["basis_z"].replace([np.inf, -np.inf], np.nan)
        # Forward 4h return
        df["mark_fwd_4h"] = df["mark"].shift(-HOLD_BARS_1H) / df["mark"] - 1.0
        df = df.dropna(subset=["basis_z", "mark_fwd_4h"])
        sym_data[sym] = df
        all_basis_pct.extend(df["basis_pct"].dropna().tolist())
        all_basis_z.extend(df["basis_z"].dropna().tolist())
        log.info(f"  {sym}: n_aligned={len(df)}, basis_pct median={df['basis_pct'].median()*1e4:.2f} bp, |z|>2 rate={(df['basis_z'].abs() > 2).mean():.2%}")

    bp_arr = np.array(all_basis_pct)
    bz_arr = np.array(all_basis_z)
    out["lesson_34_empirical_distribution"] = {
        "basis_pct_n": int(len(bp_arr)),
        "basis_pct_p01_bp": float(np.percentile(bp_arr, 1) * 1e4),
        "basis_pct_p05_bp": float(np.percentile(bp_arr, 5) * 1e4),
        "basis_pct_p50_bp": float(np.percentile(bp_arr, 50) * 1e4),
        "basis_pct_p95_bp": float(np.percentile(bp_arr, 95) * 1e4),
        "basis_pct_p99_bp": float(np.percentile(bp_arr, 99) * 1e4),
        "basis_pct_max_abs_bp": float(np.max(np.abs(bp_arr)) * 1e4),
        "basis_z_n": int(len(bz_arr)),
        "basis_z_p50": float(np.median(bz_arr)),
        "basis_z_p90": float(np.percentile(bz_arr, 90)),
        "basis_z_p99": float(np.percentile(bz_arr, 99)),
        "abs_z_gt2_rate": float((np.abs(bz_arr) > 2).mean()),
        "abs_z_gt2_n": int((np.abs(bz_arr) > 2).sum()),
        "abs_z_gt2_5_rate": float((np.abs(bz_arr) > 2.5).mean()),
        "abs_z_gt3_rate": float((np.abs(bz_arr) > 3).mean()),
    }
    log.info(f"basis_z |z|>2 rate: {out['lesson_34_empirical_distribution']['abs_z_gt2_rate']:.2%}")

    # P2: Lesson #11 — empirical event count for joint trigger HMM HIGH-vol × |basis z|>2
    # Use 1h log-return rolling 30d std as PROXY HMM HIGH-vol state (top tercile)
    # (Full HMM in R-1; proxy here suffices for sample density estimate)
    sym_joint_counts: dict[str, dict] = {}
    sym_joint_gross_a: dict[str, np.ndarray] = {}  # A focus: |z|>2 positive side, SHORT (basis rich → mean revert)
    sym_joint_gross_b: dict[str, np.ndarray] = {}  # B focus: |z|>2 negative side, LONG (basis cheap → mean revert)

    for sym, df in sym_data.items():
        # Compute realized 1h vol over rolling 30d
        df = df.copy()
        df["log_ret_1h"] = np.log(df["mark"]).diff()
        df["rv_30d"] = df["log_ret_1h"].rolling(ROLLING_WIN_1H, min_periods=ROLLING_WIN_1H // 2).std()
        df["rv_rank"] = df["rv_30d"].rank(pct=True)
        df["high_vol"] = (df["rv_rank"] >= 0.67).astype(int)  # top tercile proxy

        joint_a = df[(df["basis_z"] > 2.0) & (df["high_vol"] == 1)].copy()  # rich → mean revert: SHORT
        joint_b = df[(df["basis_z"] < -2.0) & (df["high_vol"] == 1)].copy()  # cheap → mean revert: LONG

        # Dedup serial overlap (hold 4h)
        def dedup(d: pd.DataFrame) -> pd.DataFrame:
            if len(d) == 0:
                return d
            kept = [d.index[0]]
            for ts in d.index[1:]:
                if (ts - kept[-1]).total_seconds() / 3600 >= HOLD_BARS_1H:
                    kept.append(ts)
            return d.loc[kept]

        joint_a = dedup(joint_a)
        joint_b = dedup(joint_b)

        # Gross 4h returns (no fee, no direction yet)
        a_gross = joint_a["mark_fwd_4h"].values
        b_gross = joint_b["mark_fwd_4h"].values

        # Focus direction: A_focus rich → SHORT, B_focus cheap → LONG
        # Gross (direction-applied, NO fee): a_focus = -a_gross, b_focus = +b_gross
        a_focus_gross_dir = -a_gross
        b_focus_gross_dir = b_gross

        sym_joint_gross_a[sym] = a_focus_gross_dir
        sym_joint_gross_b[sym] = b_focus_gross_dir

        sym_joint_counts[sym] = {
            "joint_a_n": int(len(joint_a)),
            "joint_b_n": int(len(joint_b)),
            "joint_a_gross_mean_bp": float(a_focus_gross_dir.mean() * 1e4) if len(a_focus_gross_dir) > 0 else None,
            "joint_b_gross_mean_bp": float(b_focus_gross_dir.mean() * 1e4) if len(b_focus_gross_dir) > 0 else None,
            "high_vol_rate": float(df["high_vol"].mean()),
        }
        log.info(
            f"  {sym}: joint_A n={len(joint_a)} gross={a_focus_gross_dir.mean()*1e4 if len(a_focus_gross_dir)>0 else 0:.2f}bp, "
            f"joint_B n={len(joint_b)} gross={b_focus_gross_dir.mean()*1e4 if len(b_focus_gross_dir)>0 else 0:.2f}bp"
        )

    out["lesson_11_sample_density"] = {
        "per_sym": sym_joint_counts,
        "total_joint_a_n": sum(v["joint_a_n"] for v in sym_joint_counts.values()),
        "total_joint_b_n": sum(v["joint_b_n"] for v in sym_joint_counts.values()),
        "expected_per_cell_per_quarter": "see total / 4 quarters / 4 quadrants approx",
        "cutoff": 30,
    }

    # Lesson #46 candidate — pool small sample gross drift
    pool_a = np.concatenate([v for v in sym_joint_gross_a.values() if len(v) > 0])
    pool_b = np.concatenate([v for v in sym_joint_gross_b.values() if len(v) > 0])

    def gross_summary(arr: np.ndarray, label: str) -> dict:
        if len(arr) < 30:
            return {"n": int(len(arr)), "insufficient": True}
        mean_bp = float(arr.mean() * 1e4)
        median_bp = float(np.median(arr) * 1e4)
        sd_bp = float(arr.std(ddof=1) * 1e4)
        se_bp = sd_bp / np.sqrt(len(arr))
        return {
            "n": int(len(arr)),
            "gross_mean_bp": mean_bp,
            "gross_median_bp": median_bp,
            "gross_sd_bp": sd_bp,
            "gross_se_bp": float(se_bp),
            "gross_ci95_lower_bp": float(mean_bp - 1.96 * se_bp),
            "gross_ci95_upper_bp": float(mean_bp + 1.96 * se_bp),
            "gross_pos_rate": float((arr > 0).mean()),
            "gross_vs_fee_floor_bp": float(abs(mean_bp) - FEE_FLOOR_BP),
            "lesson_46_pass": bool(abs(mean_bp) >= FEE_FLOOR_BP),
        }

    out["lesson_46_gross_drift_estimate"] = {
        "fee_floor_bp": FEE_FLOOR_BP,
        "A_focus_rich_SHORT": gross_summary(pool_a, "A_focus"),
        "B_focus_cheap_LONG": gross_summary(pool_b, "B_focus"),
    }

    log.info("=== Lesson #46 candidate verdict ===")
    log.info(f"A_focus (rich→SHORT) pool: {out['lesson_46_gross_drift_estimate']['A_focus_rich_SHORT']}")
    log.info(f"B_focus (cheap→LONG) pool: {out['lesson_46_gross_drift_estimate']['B_focus_cheap_LONG']}")

    # Verdict
    a_pass = out["lesson_46_gross_drift_estimate"]["A_focus_rich_SHORT"].get("lesson_46_pass", False)
    b_pass = out["lesson_46_gross_drift_estimate"]["B_focus_cheap_LONG"].get("lesson_46_pass", False)
    sample_a_ok = out["lesson_46_gross_drift_estimate"]["A_focus_rich_SHORT"].get("n", 0) >= 30
    sample_b_ok = out["lesson_46_gross_drift_estimate"]["B_focus_cheap_LONG"].get("n", 0) >= 30

    if not sample_a_ok and not sample_b_ok:
        out["verdict"] = "SAMPLE_INSUFFICIENT_R0_HALT_LESSON_11"
    elif a_pass or b_pass:
        out["verdict"] = "R0_PASS_PROCEED_R1"
    else:
        out["verdict"] = "R0_DECLINE_LESSON_46_GROSS_DRIFT_SUB_FEE_FLOOR"

    elapsed = time.time() - t0
    out["wall_clock_seconds"] = float(elapsed)
    out_path = OUTPUT_DIR / "r0_prescreen.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    log.info(f"Wrote {out_path} (wall={elapsed:.1f}s)")
    log.info(f"VERDICT: {out['verdict']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
