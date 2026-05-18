"""H1 R-2 — Walk-forward + 5-fold TS-CV stress test (Track 3 Sub-task 3B).

Stresses the R-1 PASS_R1_POSITIVE_SURPRISE_ONLY focus cell against the
fragility flags surfaced by `dart_earnings_signal_r1_per_quarter_check.py`:
  - 2025Q3 significantly negative (t=-2.88)
  - 2024Q4 sparse (n=4)
  - 2026Q1/Q2 dominant — survivorship-bias concern

R-2 falsification tracks (paradigm 87 동형 학습):
  A. Walk-forward OOS: train 2024 / test 2025-2026
  B. 5-fold blocked TS-CV: 5 × 2-quarter test blocks, per-fold 3-gate PASS/FAIL
  C. Point-in-time stable subset: stocks with full OHLCV from 2024-01-02
     (filters out post-2024 listings → reduces survivor selection)
  D. Per-date concentration cap (Lesson #19 amendment): max events/day ≤ 30%
     of focus cohort.

PASS criteria:
  - Walk-forward OOS 3-gate PASS (test period A_focus net mean > 0,
    sig_t_excess ≥ 2.0, ci_lower > 0)
  - 5-fold TS-CV per-fold PASS ≥ 3/5 (paradigm 87 R-2 failed 1/5)
  - Stable subset A_focus 3-gate PASS (survivor bias drop test)
  - Per-date concentration ≤ 30%

R-2 verdict matrix:
  ALL 4 PASS                       → PASS_R2_PROMOTE_R3
  WF PASS + TS-CV PASS only        → PASS_R2_NEEDS_STABLE_SUBSET_FIX
  WF FAIL only                     → FRAGILE_TEMPORAL_WF_FAIL (paradigm 87 동형)
  TS-CV < 3/5                      → FRAGILE_CV_FAIL
  Stable subset FAIL               → FRAGILE_SURVIVOR_BIAS
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

from scripts.research.dart_earnings_signal_r1 import (  # noqa: E402
    collect_events, compute_event_returns, build_universe, candidate_pool_returns,
    TOP_KOSPI, TOP_KOSDAQ, WINDOW_BGN, WINDOW_END, OHLCV_PAD_DAYS,
    GAP_THRESHOLD, FEE_ROUND_TRIP, HOLD_DAYS, MIN_CELL_N, OUT_DIR,
)
from scripts.research._naver_kr_equity import get_ohlcv_cached  # noqa: E402
from scripts.research._perm_utils import fee_aware_perm_test, bootstrap_ci  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("h1_r2")

# ── R-2 spec ──────────────────────────────────────────────────────────────────
TRAIN_END = "2024-12-31"
TEST_BGN = "2025-01-01"
MAX_PER_DATE_FRAC = 0.30  # Lesson #19 per-date concentration cap
TSCV_MIN_PASS = 3         # 5-fold blocked CV gate (≥3/5)
STABLE_MIN_OHLCV_ROWS = 580  # ~2.4yr trading days → listed before 2024
OUT_PATH = OUT_DIR / "h1_earnings_r2_metrics.json"


def three_gate_eval(focus: pd.DataFrame, pool_returns: np.ndarray, label: str) -> dict:
    """Apply the same 3-gate evaluation used in R-1 to an arbitrary cohort."""
    n = len(focus)
    if n < MIN_CELL_N:
        return {"label": label, "n": n, "pass_n": False, "pass_three_gate": False,
                "skip_reason": f"n<{MIN_CELL_N}"}
    returns = focus["fwd_ret_gross"].values  # already direction=+1 (LONG)
    observed_net = returns - FEE_ROUND_TRIP
    perm = fee_aware_perm_test(
        observed_net_returns=observed_net.tolist(),
        candidate_pool_returns=pool_returns.tolist(),
        fee_per_trade=FEE_ROUND_TRIP,
        n_perms=1000,
    )
    boot = bootstrap_ci(observed_net.tolist(), n_boot=2000, block_size=1)
    sig_excess = perm.get("signal_t_excess")
    ci_lower = boot.get("ci_lower")
    perm_p_above = perm.get("perm_p_one_sided_above")
    pass_three = (
        sig_excess is not None and np.isfinite(sig_excess) and sig_excess >= 2.0 and
        ci_lower is not None and np.isfinite(ci_lower) and ci_lower > 0 and
        perm_p_above is not None and np.isfinite(perm_p_above) and perm_p_above <= 0.10
    )
    t = float(observed_net.mean() / observed_net.std(ddof=1) * np.sqrt(n)) \
        if n >= 2 and observed_net.std(ddof=1) > 0 else 0.0
    return {
        "label": label,
        "n": int(n),
        "pass_n": True,
        "gross_mean_bp": float(returns.mean() * 10_000),
        "net_mean_bp": float(observed_net.mean() * 10_000),
        "t_stat": t,
        "signal_t_excess": float(sig_excess) if sig_excess is not None else None,
        "ci_lower_bp": float(ci_lower * 10_000) if ci_lower is not None else None,
        "ci_upper_bp": float(boot.get("ci_upper") * 10_000) if boot.get("ci_upper") is not None else None,
        "perm_p_one_sided_above": float(perm_p_above) if perm_p_above is not None else None,
        "pass_three_gate": bool(pass_three),
    }


def per_date_concentration(focus: pd.DataFrame) -> dict:
    if focus.empty:
        return {"max_per_date_frac": None, "pass": False}
    counts = focus["entry_date"].value_counts()
    top_date = counts.idxmax()
    top_n = int(counts.max())
    frac = top_n / len(focus)
    return {
        "max_per_date_top": str(top_date.date()) if hasattr(top_date, "date") else str(top_date),
        "max_per_date_n": top_n,
        "max_per_date_frac": float(frac),
        "cap": MAX_PER_DATE_FRAC,
        "pass": frac <= MAX_PER_DATE_FRAC,
    }


def walk_forward(focus: pd.DataFrame, pool_returns: np.ndarray) -> dict:
    train = focus[focus["entry_date"] <= pd.Timestamp(TRAIN_END)]
    test = focus[focus["entry_date"] >= pd.Timestamp(TEST_BGN)]
    return {
        "train_window": f"<= {TRAIN_END}",
        "test_window": f">= {TEST_BGN}",
        "train": three_gate_eval(train, pool_returns, "train"),
        "test":  three_gate_eval(test,  pool_returns, "test"),
    }


def five_fold_tscv(focus: pd.DataFrame, pool_returns: np.ndarray) -> dict:
    """5 blocked test folds × 2 quarters each, in chronological order.
    Each fold reports 3-gate PASS/FAIL on its 2-quarter test cohort."""
    focus = focus.copy()
    focus["quarter"] = focus["entry_date"].dt.to_period("Q").astype(str)
    quarters = sorted(focus["quarter"].unique())
    # Build folds of 2 consecutive quarters; if leftover 1 Q, merge into last fold
    folds = []
    i = 0
    while i < len(quarters):
        chunk = quarters[i:i + 2]
        if len(chunk) == 1 and folds:
            folds[-1].extend(chunk)
        else:
            folds.append(chunk)
        i += 2
    fold_results = []
    for k, qs in enumerate(folds, 1):
        cohort = focus[focus["quarter"].isin(qs)]
        r = three_gate_eval(cohort, pool_returns, f"fold_{k}({'+'.join(qs)})")
        r["quarters"] = qs
        fold_results.append(r)
    n_pass = sum(1 for r in fold_results if r.get("pass_three_gate"))
    return {
        "fold_count": len(fold_results),
        "tscv_min_pass": TSCV_MIN_PASS,
        "n_pass": n_pass,
        "pass": n_pass >= TSCV_MIN_PASS,
        "folds": fold_results,
    }


def stable_subset(focus: pd.DataFrame, all_events: pd.DataFrame,
                  pool_returns: np.ndarray, ohlcv_bgn: str, ohlcv_end: str) -> dict:
    """Filter to stocks with ≥ STABLE_MIN_OHLCV_ROWS bars 2024-01-01 .. 2026-04-30.
    Removes post-2024 listings (largest survivorship contributor)."""
    rows_per_code: dict[str, int] = {}
    for code in focus["stock_code"].unique():
        df = get_ohlcv_cached(code, ohlcv_bgn, ohlcv_end)
        rows_per_code[code] = len(df)
    stable_codes = {c for c, n in rows_per_code.items() if n >= STABLE_MIN_OHLCV_ROWS}
    log.info("stable subset: %d / %d focus stocks have ≥%d OHLCV rows",
             len(stable_codes), len(focus["stock_code"].unique()), STABLE_MIN_OHLCV_ROWS)
    stable_focus = focus[focus["stock_code"].isin(stable_codes)]
    return {
        "min_ohlcv_rows": STABLE_MIN_OHLCV_ROWS,
        "n_stable_stocks": len(stable_codes),
        "n_focus_stocks": int(focus["stock_code"].nunique()),
        "n_dropped_events": int(len(focus) - len(stable_focus)),
        "stable_evaluation": three_gate_eval(stable_focus, pool_returns, "stable_subset"),
    }


def verdict(wf: dict, cv: dict, stable: dict, perdate: dict) -> str:
    wf_pass = wf["test"].get("pass_three_gate", False)
    cv_pass = cv.get("pass", False)
    stable_pass = stable["stable_evaluation"].get("pass_three_gate", False)
    pd_pass = perdate.get("pass", False)

    if all([wf_pass, cv_pass, stable_pass, pd_pass]):
        return "PASS_R2_PROMOTE_R3"
    if wf_pass and cv_pass and not stable_pass:
        return "FRAGILE_SURVIVOR_BIAS"
    if not wf_pass:
        return "FRAGILE_TEMPORAL_WF_FAIL"  # paradigm 87 동형
    if not cv_pass:
        return "FRAGILE_CV_FAIL"
    if not pd_pass:
        return "FRAGILE_PER_DATE_CONCENTRATION"
    return "FAIL_MIXED"


def main():
    log.info("=== H1 R-2: walk-forward + 5-fold TS-CV stress test ===")
    universe = build_universe(TOP_KOSPI, TOP_KOSDAQ)
    universe_codes = set(universe["itemCode"].astype(str).str.zfill(6).tolist())
    events = collect_events(universe_codes)

    ohlcv_bgn = (pd.to_datetime(WINDOW_BGN, format="%Y%m%d")
                 - pd.Timedelta(days=OHLCV_PAD_DAYS)).strftime("%Y%m%d")
    ohlcv_end = (pd.to_datetime(WINDOW_END, format="%Y%m%d")
                 + pd.Timedelta(days=OHLCV_PAD_DAYS)).strftime("%Y%m%d")

    events_ret = compute_event_returns(events, ohlcv_bgn, ohlcv_end)
    log.info("events with valid returns: %d", len(events_ret))

    # A_focus cohort: pos_gap ≥ +3%, LONG direction implied (gross is open->close)
    focus = events_ret[events_ret["gap"] >= GAP_THRESHOLD].reset_index(drop=True)
    log.info("focus cohort (pos_gap × LONG): n=%d, stocks=%d",
             len(focus), focus["stock_code"].nunique())

    pool = candidate_pool_returns(events_ret, ohlcv_bgn, ohlcv_end)
    log.info("candidate pool returns: %d", len(pool))

    wf = walk_forward(focus, pool)
    cv = five_fold_tscv(focus, pool)
    stable = stable_subset(focus, events_ret, pool, ohlcv_bgn, ohlcv_end)
    perdate = per_date_concentration(focus)

    summary = {
        "hypothesis": "H1_gap_proxy_R2",
        "design": {
            "cohort": "A_focus = pos_gap ≥ +3% × LONG +5d hold",
            "n_focus": int(len(focus)),
            "fee_round_trip_bp": int(FEE_ROUND_TRIP * 10_000),
            "tscv_min_pass": TSCV_MIN_PASS,
            "max_per_date_frac": MAX_PER_DATE_FRAC,
            "stable_min_ohlcv_rows": STABLE_MIN_OHLCV_ROWS,
        },
        "walk_forward": wf,
        "tscv_5fold": cv,
        "stable_subset": stable,
        "per_date_concentration": perdate,
        "verdict": verdict(wf, cv, stable, perdate),
    }

    def _clean(o):
        if isinstance(o, float):
            return None if not np.isfinite(o) else o
        if isinstance(o, dict):
            return {k: _clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [_clean(v) for v in o]
        return o
    OUT_PATH.write_text(json.dumps(_clean(summary), ensure_ascii=False, indent=2))
    log.info("WROTE %s", OUT_PATH)
    print(json.dumps({
        "verdict": summary["verdict"],
        "wf_test_pass": summary["walk_forward"]["test"].get("pass_three_gate"),
        "tscv_pass": f"{cv['n_pass']}/{cv['fold_count']}",
        "stable_pass": summary["stable_subset"]["stable_evaluation"].get("pass_three_gate"),
        "per_date_pass": perdate.get("pass"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
