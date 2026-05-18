"""H1 R-2c — TRUE YoY-surprise variant (Track 3 Sub-task 3B).

Replaces the R-2 gap proxy with **DART fnltt YoY surprise**:
  surprise = (this_quarter_OP - same_quarter_prior_year_OP) / |prior_year_OP|

Threshold: surprise ≥ +30% = positive surprise (top quintile, paper convention).
This is the "true" earnings surprise — not the observable gap — and answers:
  "Does post-earnings drift exist for genuine fundamental positive surprises,
   or was the R-1 gap signal just a 2026 KR market regime artifact?"

Tests same 5-fold blocked TS-CV as R-2. If true-surprise variant PASSES TS-CV
(≥ 3/5 folds), the R-2 gap proxy failed due to mixing genuine surprises with
sentiment-driven gaps. If it FAILS the same way, the per-Q regime concentration
is structural — confirms graveyard verdict.

Cohort definition:
  trigger: 잠정실적 disclosure with yoy_op_growth ≥ +30%
  entry:   next trading day open (same as R-1/R-2)
  exit:    +5d close
  fee:     50bp round-trip
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

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

from app.services.dart_adapter import fnltt_singl_acnt, DartError  # noqa: E402
from scripts.research.dart_earnings_signal_r1 import (  # noqa: E402
    collect_events, compute_event_returns, build_universe, candidate_pool_returns,
    TOP_KOSPI, TOP_KOSDAQ, WINDOW_BGN, WINDOW_END, OHLCV_PAD_DAYS,
    FEE_ROUND_TRIP, HOLD_DAYS, MIN_CELL_N, OUT_DIR,
)
from scripts.research._perm_utils import fee_aware_perm_test, bootstrap_ci  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("h1_r2c")

# ── Config ────────────────────────────────────────────────────────────────────
SURPRISE_THRESHOLD = 0.30      # YoY ≥ +30% = positive surprise
TSCV_MIN_PASS = 3              # 5-fold blocked TS-CV gate
FNLTT_CACHE_DIR = ROOT / "runs" / "dart_track" / "fnltt_cache"
EVENTS_RET_CACHE = ROOT / "runs" / "dart_track" / "events_ret_cache.joblib"
OUT_PATH = OUT_DIR / "h1_earnings_r2c_metrics.json"


# ── Quarter inference + fnltt fetch ───────────────────────────────────────────
def quarter_from_rcept_dt(rcept_dt: pd.Timestamp) -> tuple[int, str]:
    """Infer (bsns_year, reprt_code) from filing date.
    잠정실적 typically filed 30-45d after quarter end."""
    m = rcept_dt.month
    if 4 <= m <= 6:    # Q1 filed Apr-Jun
        return rcept_dt.year, "11013"
    if 7 <= m <= 9:    # Q2 filed Jul-Sep
        return rcept_dt.year, "11012"
    if 10 <= m <= 12:  # Q3 filed Oct-Dec
        return rcept_dt.year, "11014"
    # Jan-Mar: Q4 of prior year
    return rcept_dt.year - 1, "11011"


def _fnltt_cache_path(corp_code: str, year: int, rcd: str) -> Path:
    FNLTT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return FNLTT_CACHE_DIR / f"{corp_code}_{year}_{rcd}.joblib"


def fnltt_yoy_op(corp_code: str, bsns_year: int, reprt_code: str) -> dict | None:
    """Returns {'op_curr', 'op_yoy', 'op_growth', 'rev_curr', 'rev_yoy', 'rev_growth'}
    using consolidated (CFS) if available, else separate (OFS).
    Cached to disk per (corp_code, year, rcd)."""
    cache = _fnltt_cache_path(corp_code, bsns_year, reprt_code)
    if cache.exists():
        return joblib.load(cache)

    result = None
    try:
        d = fnltt_singl_acnt(corp_code, str(bsns_year), reprt_code)
        rows = d.get("list", []) or []
    except DartError as e:
        log.debug("fnltt %s/%s/%s FAIL %s", corp_code, bsns_year, reprt_code, e.status)
        rows = []

    if rows:
        # Filter sj_div=IS (income statement) and extract OP / 매출 by fs_div
        is_rows = [r for r in rows if r.get("sj_div") == "IS"]
        # Prefer CFS if present (multiple "영업이익" rows may exist, first = consolidated)
        op_curr = op_yoy = rev_curr = rev_yoy = None
        for r in is_rows:
            nm = (r.get("account_nm") or "").strip()
            if nm == "영업이익" and op_curr is None:
                op_curr = _to_num(r.get("thstrm_amount"))
                op_yoy = _to_num(r.get("frmtrm_amount"))
            elif nm == "매출액" and rev_curr is None:
                rev_curr = _to_num(r.get("thstrm_amount"))
                rev_yoy = _to_num(r.get("frmtrm_amount"))
        if op_curr is not None and op_yoy is not None and abs(op_yoy) > 1e-6:
            result = {
                "op_curr": op_curr, "op_yoy": op_yoy,
                "op_growth": (op_curr - op_yoy) / abs(op_yoy),
                "rev_curr": rev_curr, "rev_yoy": rev_yoy,
                "rev_growth": ((rev_curr - rev_yoy) / abs(rev_yoy)) if rev_yoy else None,
            }
    # Cache even None to avoid re-fetching (use empty dict to distinguish)
    joblib.dump(result if result is not None else {}, cache)
    return result


def _to_num(s):
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    t = str(s).replace(",", "").strip()
    if not t or t in ("-", "—"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def enrich_with_yoy(events_ret: pd.DataFrame) -> pd.DataFrame:
    """For each event, look up YoY OP surprise via DART fnltt.
    Adds columns: bsns_year, reprt_code, op_curr, op_yoy, op_growth."""
    out = []
    n = len(events_ret)
    last_call_ts = 0.0
    for i, (_, ev) in enumerate(events_ret.iterrows(), 1):
        corp_code = ev.get("corp_code") or ""
        if not corp_code or len(corp_code) != 8:
            continue
        rcept_dt = ev["rcept_dt"]
        bsns_year, rcd = quarter_from_rcept_dt(rcept_dt)
        # Rate-limit: ≥ 0.05s between fnltt calls (well under 20K/day quota)
        cache = _fnltt_cache_path(corp_code, bsns_year, rcd)
        if not cache.exists():
            elapsed = time.time() - last_call_ts
            if elapsed < 0.05:
                time.sleep(0.05 - elapsed)
            last_call_ts = time.time()
        info = fnltt_yoy_op(corp_code, bsns_year, rcd)
        row = ev.to_dict()
        row.update({"bsns_year": bsns_year, "reprt_code": rcd})
        if info:
            row.update(info)
        out.append(row)
        if i % 200 == 0:
            log.info("  enrich %d/%d events", i, n)
    return pd.DataFrame(out)


# ── Reuse R-2 test machinery, but on yoy_op_growth-defined cohort ────────────
def three_gate_eval(focus: pd.DataFrame, pool_returns: np.ndarray, label: str) -> dict:
    n = len(focus)
    if n < MIN_CELL_N:
        return {"label": label, "n": n, "pass_n": False, "pass_three_gate": False,
                "skip_reason": f"n<{MIN_CELL_N}"}
    returns = focus["fwd_ret_gross"].values
    observed_net = returns - FEE_ROUND_TRIP
    perm = fee_aware_perm_test(
        observed_net_returns=observed_net.tolist(),
        candidate_pool_returns=pool_returns.tolist(),
        fee_per_trade=FEE_ROUND_TRIP, n_perms=1000,
    )
    boot = bootstrap_ci(observed_net.tolist(), n_boot=2000, block_size=1)
    sig = perm.get("signal_t_excess"); ci_lo = boot.get("ci_lower")
    p_above = perm.get("perm_p_one_sided_above")
    pass_three = (
        sig is not None and np.isfinite(sig) and sig >= 2.0
        and ci_lo is not None and np.isfinite(ci_lo) and ci_lo > 0
        and p_above is not None and np.isfinite(p_above) and p_above <= 0.10
    )
    t = float(observed_net.mean() / observed_net.std(ddof=1) * np.sqrt(n)) \
        if n >= 2 and observed_net.std(ddof=1) > 0 else 0.0
    return {
        "label": label, "n": int(n), "pass_n": True,
        "gross_mean_bp": float(returns.mean() * 10_000),
        "net_mean_bp": float(observed_net.mean() * 10_000),
        "t_stat": t,
        "signal_t_excess": float(sig) if sig is not None else None,
        "ci_lower_bp": float(ci_lo * 10_000) if ci_lo is not None else None,
        "perm_p_one_sided_above": float(p_above) if p_above is not None else None,
        "pass_three_gate": bool(pass_three),
    }


def five_fold_tscv(focus: pd.DataFrame, pool_returns: np.ndarray) -> dict:
    focus = focus.copy()
    focus["quarter"] = focus["entry_date"].dt.to_period("Q").astype(str)
    quarters = sorted(focus["quarter"].unique())
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
    return {"fold_count": len(fold_results), "n_pass": n_pass,
            "pass": n_pass >= TSCV_MIN_PASS, "folds": fold_results}


def main():
    log.info("=== H1 R-2c: TRUE YoY-surprise variant ===")
    log.info("surprise_threshold yoy_op_growth ≥ +%.0f%%, fee_RT=%.0fbp, hold=%dd",
             SURPRISE_THRESHOLD * 100, FEE_ROUND_TRIP * 10_000, HOLD_DAYS)

    # 1. Load events with corp_code (re-collect via R-1 helper; uses DART)
    universe = build_universe(TOP_KOSPI, TOP_KOSDAQ)
    universe_codes = set(universe["itemCode"].astype(str).str.zfill(6).tolist())

    if EVENTS_RET_CACHE.exists():
        log.info("loading cached events_ret from %s", EVENTS_RET_CACHE)
        events_ret = joblib.load(EVENTS_RET_CACHE)
    else:
        events = collect_events(universe_codes)
        ohlcv_bgn = (pd.to_datetime(WINDOW_BGN, format="%Y%m%d")
                     - pd.Timedelta(days=OHLCV_PAD_DAYS)).strftime("%Y%m%d")
        ohlcv_end = (pd.to_datetime(WINDOW_END, format="%Y%m%d")
                     + pd.Timedelta(days=OHLCV_PAD_DAYS)).strftime("%Y%m%d")
        events_ret = compute_event_returns(events, ohlcv_bgn, ohlcv_end)
        joblib.dump(events_ret, EVENTS_RET_CACHE)
        log.info("cached events_ret -> %s", EVENTS_RET_CACHE)
    log.info("events with returns: %d", len(events_ret))

    # 2. Enrich with YoY OP surprise via DART fnltt
    log.info("fnltt YoY enrichment (cached per (corp,year,rcd))")
    events_enriched = enrich_with_yoy(events_ret)
    n_with_growth = int(events_enriched["op_growth"].notna().sum()) if "op_growth" in events_enriched.columns else 0
    log.info("events with op_growth available: %d / %d", n_with_growth, len(events_enriched))

    if n_with_growth == 0:
        OUT_PATH.write_text(json.dumps({"verdict": "FAIL_NO_FNLTT_DATA"}))
        return

    # 3. Build surprise cohorts
    valid = events_enriched.dropna(subset=["op_growth", "fwd_ret_gross"]).copy()
    pos = valid[valid["op_growth"] >= SURPRISE_THRESHOLD]
    neg = valid[valid["op_growth"] <= -SURPRISE_THRESHOLD]
    mid = valid[(valid["op_growth"] > -SURPRISE_THRESHOLD) &
                (valid["op_growth"] < SURPRISE_THRESHOLD)]
    log.info("YoY OP surprise distribution: pos(≥+30%%)=%d  neg(≤-30%%)=%d  mid=%d",
             len(pos), len(neg), len(mid))

    # 4. Candidate pool (gross 5d-hold returns across universe — same as R-1/R-2)
    pool = candidate_pool_returns(events_ret,
        (pd.to_datetime(WINDOW_BGN, format="%Y%m%d") - pd.Timedelta(days=OHLCV_PAD_DAYS)).strftime("%Y%m%d"),
        (pd.to_datetime(WINDOW_END, format="%Y%m%d") + pd.Timedelta(days=OHLCV_PAD_DAYS)).strftime("%Y%m%d"))
    log.info("candidate pool: %d", len(pool))

    # 5. Aggregate + TS-CV evaluations for the positive-surprise cohort
    pos_aggregate = three_gate_eval(pos, pool, "pos_surprise_aggregate")
    pos_tscv = five_fold_tscv(pos, pool)
    # Mirror sanity (LONG when surprise is NEG should fail)
    neg_aggregate = three_gate_eval(neg, pool, "neg_surprise_LONG_mirror_sanity")

    # 6. Comparison vs R-1/R-2 gap proxy cohort (read prior result, derive overlap)
    summary = {
        "hypothesis": "H1_yoy_surprise_R2c",
        "design": {
            "surprise_threshold": SURPRISE_THRESHOLD,
            "fee_round_trip_bp": int(FEE_ROUND_TRIP * 10_000),
            "hold_days": HOLD_DAYS,
            "tscv_min_pass": TSCV_MIN_PASS,
        },
        "totals": {
            "n_events_total": int(len(events_enriched)),
            "n_with_op_growth": n_with_growth,
            "n_pos_surprise": int(len(pos)),
            "n_neg_surprise": int(len(neg)),
            "n_mid": int(len(mid)),
        },
        "pos_surprise_aggregate": pos_aggregate,
        "pos_surprise_5fold_tscv": pos_tscv,
        "neg_surprise_LONG_mirror_sanity": neg_aggregate,
        "comparison_with_r2_gap_proxy": {
            "r2_gap_proxy_aggregate_pass": True,    # from R-2 results
            "r2_gap_proxy_tscv_pass_ratio": "1/5",  # from R-2 results
            "r2c_yoy_aggregate_pass": pos_aggregate.get("pass_three_gate"),
            "r2c_yoy_tscv_pass_ratio": f"{pos_tscv['n_pass']}/{pos_tscv['fold_count']}",
        },
        "verdict": _verdict(pos_aggregate, pos_tscv),
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
        "n_pos_surprise": int(len(pos)),
        "aggregate_pass": pos_aggregate.get("pass_three_gate"),
        "tscv_pass": f"{pos_tscv['n_pass']}/{pos_tscv['fold_count']}",
    }, ensure_ascii=False))


def _verdict(agg: dict, cv: dict) -> str:
    if agg.get("pass_three_gate") and cv.get("pass"):
        return "PASS_R2C_TRUE_SURPRISE_PROMOTE_R3"
    if agg.get("pass_three_gate") and not cv.get("pass"):
        return "FRAGILE_TRUE_SURPRISE_AGG_ONLY"
    if not agg.get("pass_three_gate") and cv.get("pass"):
        return "AMBIGUOUS_TSCV_PASS_AGG_FAIL"
    return "GRAVEYARD_TRUE_SURPRISE_ALSO_FAIL"


if __name__ == "__main__":
    main()
