"""H2 R-1 — 가이던스 변경 ≥30% momentum (Track 3 Sub-task 3B).

Hypothesis:
  "매출액또는손익구조30%(대규모법인은15%)이상변경" 공정공시 발표 후 +1d 시가 매수 → +5d hold.
  Direction by fnltt YoY OP growth 동일 분기 (≥+30% pos / ≤-30% neg).
  4-quadrant Symmetric Negative Test + Lesson #29 cross-proxy (observable + fundamental).

Lesson #29 강제 적용 (paradigm 92 trap 방지):
  Observable proxy: pre-event gap or prior 5d return (sentiment signal)
  Fundamental signal: fnltt YoY OP growth from DART (true magnitude + direction)

  Both must independently PASS to qualify as a genuine paradigm.
  Single-proxy PASS = false discovery (H1 잠정실적 gap_proxy 동형 trap).

Test design:
  Universe: top-200 KOSPI + top-150 KOSDAQ (build_universe joblib reuse)
  Window:   2024-01-01 .. 2026-04-30 (2.4yr; identical to H1)
  Trigger:  EARNINGS_GUIDANCE_AMEND classifier match (track3 §6.1 Tier S)
  Entry:    next trading day open after rcept_dt
  Exit:     +5 trading days close
  Fee:      50bp KR equity round-trip

4-quadrant (direction by YoY OP growth):
  A focus     : op_growth ≥ +30% × LONG
  A mirror    : op_growth ≥ +30% × SHORT
  B same-sign : op_growth ≤ -30% × SHORT
  B mirror    : op_growth ≤ -30% × LONG

Lesson grid:
  #11 sample density (per-cell n ≥ 30)
  #19 4-quadrant Symmetric Negative Test
  #26 Concentration Gate + 5-fold blocked TS-CV
  #27 entry_immediate (가이던스 공시 = immediate; classifier)
  #28 substrate availability (DART rcept_dt same-day publish)
  #29 cross-proxy strict (BOTH observable AND fundamental tracks must PASS)

Output: backend/runs/dart_track/h2_guidance_r1_metrics.json
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

from app.services.dart_adapter import iter_disclosures_chunked  # noqa: E402
from app.services.disclosure_parser import classify, EARNINGS_GUIDANCE_AMEND  # noqa: E402
from scripts.research._naver_kr_equity import (  # noqa: E402
    build_universe, get_ohlcv_cached, warm_cache,
)
from scripts.research._perm_utils import fee_aware_perm_test, bootstrap_ci  # noqa: E402
from scripts.research.dart_earnings_signal_r1 import (  # noqa: E402
    compute_event_returns, candidate_pool_returns, cell_stats,
    TOP_KOSPI, TOP_KOSDAQ, WINDOW_BGN, WINDOW_END, OHLCV_PAD_DAYS,
    HOLD_DAYS, FEE_ROUND_TRIP, MIN_CELL_N, MAX_SYMBOL_FRACTION,
)
from scripts.research.dart_earnings_signal_r2c import (  # noqa: E402
    quarter_from_rcept_dt, fnltt_yoy_op, _fnltt_cache_path,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("h2_r1")

# ── Config ────────────────────────────────────────────────────────────────────
GROWTH_THRESHOLD = 0.30        # YoY OP/Rev ≥ +30% = positive (Lesson #29 fundamental)
PRE_RET_LOOKBACK_DAYS = 5      # observable sentiment proxy: prior 5d return
TSCV_MIN_PASS = 3              # 5-fold blocked TS-CV gate (paradigm 92 lesson)
OUT_DIR = ROOT / "runs" / "dart_track"
OUT_PATH = OUT_DIR / "h2_guidance_r1_metrics.json"
GUIDANCE_EVENTS_CACHE = OUT_DIR / "h2_guidance_events_cache.joblib"
GUIDANCE_EVENTS_RET_CACHE = OUT_DIR / "h2_guidance_events_ret_cache.joblib"


# ── Step 1: collect guidance events ──────────────────────────────────────────
def collect_guidance_events(universe_codes: set[str]) -> pd.DataFrame:
    """Sweep DART list.json over 2.4yr for KOSPI + KOSDAQ, keep events whose
    classifier matches EARNINGS_GUIDANCE_AMEND. Cached to disk."""
    if GUIDANCE_EVENTS_CACHE.exists():
        log.info("loading cached guidance events from %s", GUIDANCE_EVENTS_CACHE)
        return joblib.load(GUIDANCE_EVENTS_CACHE)

    rows = []
    for corp_cls in ("Y", "K"):
        log.info("DART sweep corp_cls=%s (guidance ≥30% disclosures)", corp_cls)
        cnt_seen = cnt_kept = 0
        for r in iter_disclosures_chunked(
            bgn_de=WINDOW_BGN, end_de=WINDOW_END,
            corp_cls=corp_cls, pblntf_ty="I", chunk_days=30,
        ):
            cnt_seen += 1
            nm = r.get("report_nm", "") or ""
            kind = classify(nm)
            if kind is not EARNINGS_GUIDANCE_AMEND:
                continue
            code = (r.get("stock_code") or "").strip()
            if code not in universe_codes:
                continue
            rows.append({
                "rcept_dt": r["rcept_dt"],
                "rcept_no": r.get("rcept_no"),
                "stock_code": code,
                "corp_code": (r.get("corp_code") or "").strip(),
                "corp_cls": corp_cls,
                "corp_name": r.get("corp_name"),
                "report_nm": nm.strip(),
            })
            cnt_kept += 1
        log.info("corp_cls=%s seen=%d guidance_kept=%d", corp_cls, cnt_seen, cnt_kept)
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates(subset=["rcept_no"]).reset_index(drop=True)
        df["rcept_dt"] = pd.to_datetime(df["rcept_dt"], format="%Y%m%d")
    joblib.dump(df, GUIDANCE_EVENTS_CACHE)
    log.info("cached guidance events -> %s", GUIDANCE_EVENTS_CACHE)
    return df


# ── Step 2: enrich with YoY OP + pre-event observable sentiment ──────────────
def enrich_with_yoy_and_pre_ret(events_ret: pd.DataFrame) -> pd.DataFrame:
    """Add columns:
      bsns_year, reprt_code, op_curr, op_yoy, op_growth, rev_growth (fundamental)
      pre_ret_5d (observable sentiment proxy: prior 5d close-to-close ret before event)
    """
    out = []
    n = len(events_ret)
    last_call_ts = 0.0
    for i, (_, ev) in enumerate(events_ret.iterrows(), 1):
        corp_code = ev.get("corp_code") or ""
        if not corp_code or len(corp_code) != 8:
            out.append(ev.to_dict())
            continue
        rcept_dt = ev["rcept_dt"]
        bsns_year, rcd = quarter_from_rcept_dt(rcept_dt)
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
            log.info("  yoy enrich %d/%d", i, n)
    df = pd.DataFrame(out)
    return df


def compute_pre_event_returns(events_ret: pd.DataFrame, ohlcv_bgn: str,
                              ohlcv_end: str) -> pd.DataFrame:
    """Compute pre_ret_5d (close-to-close return over the 5d preceding rcept_dt).
    This is the observable sentiment proxy for Lesson #29 cross-proxy split."""
    out_rows = []
    by_code = events_ret.groupby("stock_code")
    for code, grp in by_code:
        df = get_ohlcv_cached(code, ohlcv_bgn, ohlcv_end)
        if df.empty:
            for _, ev in grp.iterrows():
                row = ev.to_dict()
                row["pre_ret_5d"] = np.nan
                out_rows.append(row)
            continue
        df = df.set_index("date").sort_index()
        dates_array = df.index.values
        for _, ev in grp.iterrows():
            ev_dt = ev["rcept_dt"].to_datetime64()
            pos = int(np.searchsorted(dates_array, ev_dt, side="right"))
            # Need prior_close at pos-1 and close 5d earlier at pos-1-PRE
            if pos - 1 - PRE_RET_LOOKBACK_DAYS < 0 or pos < 1:
                row = ev.to_dict()
                row["pre_ret_5d"] = np.nan
                out_rows.append(row)
                continue
            c_end = float(df["close"].iloc[pos - 1])
            c_beg = float(df["close"].iloc[pos - 1 - PRE_RET_LOOKBACK_DAYS])
            row = ev.to_dict()
            row["pre_ret_5d"] = (c_end / c_beg - 1.0) if (c_beg > 0 and c_end > 0) else np.nan
            out_rows.append(row)
    return pd.DataFrame(out_rows)


# ── Step 3: 4-quadrant on fundamental direction (YoY OP) ─────────────────────
def run_quadrant_by_yoy(events_ret: pd.DataFrame, pool_returns: np.ndarray,
                        track_label: str) -> dict:
    """4-quadrant Symmetric Negative Test, direction by YoY OP growth."""
    if events_ret.empty:
        return {"error": "events_ret empty"}
    if "op_growth" not in events_ret.columns:
        return {"error": "op_growth column missing"}

    valid = events_ret.dropna(subset=["op_growth", "fwd_ret_gross"])
    pos = valid[valid["op_growth"] >= GROWTH_THRESHOLD]
    neg = valid[valid["op_growth"] <= -GROWTH_THRESHOLD]

    def per_sym_counts(df):
        return df["stock_code"].value_counts().to_dict()

    quadrants = {
        "A_focus_pos_long":   {"df": pos, "dir": +1, "label": f"{track_label} pos_yoy × LONG"},
        "A_mirror_pos_short": {"df": pos, "dir": -1, "label": f"{track_label} pos_yoy × SHORT"},
        "B_same_neg_short":   {"df": neg, "dir": -1, "label": f"{track_label} neg_yoy × SHORT"},
        "B_mirror_neg_long":  {"df": neg, "dir": +1, "label": f"{track_label} neg_yoy × LONG"},
    }
    out = {}
    for key, spec in quadrants.items():
        df = spec["df"]
        if df.empty:
            out[key] = cell_stats(np.array([]), spec["dir"], spec["label"])
            continue
        returns = df["fwd_ret_gross"].values
        cell = cell_stats(returns, spec["dir"], spec["label"],
                          by_symbol_count=per_sym_counts(df),
                          total_symbol_trades=len(df))
        observed_net = returns * spec["dir"] - FEE_ROUND_TRIP
        perm = fee_aware_perm_test(
            observed_net_returns=observed_net.tolist(),
            candidate_pool_returns=(pool_returns * spec["dir"]).tolist(),
            fee_per_trade=FEE_ROUND_TRIP, n_perms=1000,
        )
        boot = bootstrap_ci(observed_net.tolist(), n_boot=2000, block_size=1)
        cell.update({
            "signal_t_excess": perm["signal_t_excess"],
            "perm_p_two_sided": perm["perm_p_two_sided"],
            "perm_p_one_sided_above": perm["perm_p_one_sided_above"],
            "null_mean_t": perm["null_mean_t"],
            "ci_lower_bp": float(boot["ci_lower"] * 10_000) if boot.get("ci_lower") is not None else None,
            "ci_upper_bp": float(boot["ci_upper"] * 10_000) if boot.get("ci_upper") is not None else None,
            "prob_positive": boot.get("prob_positive"),
        })
        passes = (
            cell["pass_n"]
            and cell.get("signal_t_excess") is not None and cell["signal_t_excess"] >= 2.0
            and cell.get("ci_lower_bp") is not None and cell["ci_lower_bp"] > 0
            and cell.get("perm_p_one_sided_above") is not None and cell["perm_p_one_sided_above"] <= 0.10
        )
        cell["pass_three_gate"] = bool(passes)
        out[key] = cell
    return out


def run_quadrant_by_pre_ret(events_ret: pd.DataFrame, pool_returns: np.ndarray,
                            threshold: float = 0.03) -> dict:
    """Observable proxy track: direction by pre_ret_5d sign (sentiment proxy).
    threshold: ±3% over 5d prior — matches H1 gap threshold scale."""
    if events_ret.empty or "pre_ret_5d" not in events_ret.columns:
        return {"error": "pre_ret_5d missing"}
    valid = events_ret.dropna(subset=["pre_ret_5d", "fwd_ret_gross"])
    pos = valid[valid["pre_ret_5d"] >= threshold]
    neg = valid[valid["pre_ret_5d"] <= -threshold]

    def per_sym_counts(df):
        return df["stock_code"].value_counts().to_dict()

    quadrants = {
        "A_focus_pos_long":   {"df": pos, "dir": +1, "label": "OBS pos_pre_ret × LONG"},
        "A_mirror_pos_short": {"df": pos, "dir": -1, "label": "OBS pos_pre_ret × SHORT"},
        "B_same_neg_short":   {"df": neg, "dir": -1, "label": "OBS neg_pre_ret × SHORT"},
        "B_mirror_neg_long":  {"df": neg, "dir": +1, "label": "OBS neg_pre_ret × LONG"},
    }
    out = {}
    for key, spec in quadrants.items():
        df = spec["df"]
        if df.empty:
            out[key] = cell_stats(np.array([]), spec["dir"], spec["label"])
            continue
        returns = df["fwd_ret_gross"].values
        cell = cell_stats(returns, spec["dir"], spec["label"],
                          by_symbol_count=per_sym_counts(df),
                          total_symbol_trades=len(df))
        observed_net = returns * spec["dir"] - FEE_ROUND_TRIP
        perm = fee_aware_perm_test(
            observed_net_returns=observed_net.tolist(),
            candidate_pool_returns=(pool_returns * spec["dir"]).tolist(),
            fee_per_trade=FEE_ROUND_TRIP, n_perms=1000,
        )
        boot = bootstrap_ci(observed_net.tolist(), n_boot=2000, block_size=1)
        cell.update({
            "signal_t_excess": perm["signal_t_excess"],
            "perm_p_one_sided_above": perm["perm_p_one_sided_above"],
            "ci_lower_bp": float(boot["ci_lower"] * 10_000) if boot.get("ci_lower") is not None else None,
            "ci_upper_bp": float(boot["ci_upper"] * 10_000) if boot.get("ci_upper") is not None else None,
        })
        passes = (
            cell["pass_n"]
            and cell.get("signal_t_excess") is not None and cell["signal_t_excess"] >= 2.0
            and cell.get("ci_lower_bp") is not None and cell["ci_lower_bp"] > 0
            and cell.get("perm_p_one_sided_above") is not None and cell["perm_p_one_sided_above"] <= 0.10
        )
        cell["pass_three_gate"] = bool(passes)
        out[key] = cell
    return out


# ── Step 4: 5-fold blocked TS-CV on A focus (fundamental track) ──────────────
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


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log.info("=== H2 R-1: 가이던스 ≥30% 변경 momentum + Lesson #29 cross-proxy ===")
    log.info("Universe: top-%d KOSPI + top-%d KOSDAQ", TOP_KOSPI, TOP_KOSDAQ)
    log.info("Window: %s..%s, hold=%dd, fee_RT=%dbp, growth_thr=±%.0f%%",
             WINDOW_BGN, WINDOW_END, HOLD_DAYS, int(FEE_ROUND_TRIP * 10_000),
             GROWTH_THRESHOLD * 100)

    universe = build_universe(TOP_KOSPI, TOP_KOSDAQ)
    universe_codes = set(universe["itemCode"].astype(str).str.zfill(6).tolist())
    log.info("universe size: %d", len(universe_codes))

    # Step 1: collect guidance events
    events = collect_guidance_events(universe_codes)
    log.info("guidance events kept: %d (across %d distinct stocks)",
             len(events), events["stock_code"].nunique() if not events.empty else 0)
    if events.empty:
        OUT_PATH.write_text(json.dumps({"status": "no_events"}))
        return

    # Step 2: compute event returns + warm OHLCV cache
    ohlcv_bgn = (pd.to_datetime(WINDOW_BGN, format="%Y%m%d")
                 - pd.Timedelta(days=OHLCV_PAD_DAYS)).strftime("%Y%m%d")
    ohlcv_end = (pd.to_datetime(WINDOW_END, format="%Y%m%d")
                 + pd.Timedelta(days=OHLCV_PAD_DAYS)).strftime("%Y%m%d")
    codes_to_fetch = sorted(events["stock_code"].unique())
    log.info("warming OHLCV cache for %d codes (cache reuse from H1)", len(codes_to_fetch))
    warm_cache(codes_to_fetch, ohlcv_bgn, ohlcv_end, sleep_s=0.08)

    if GUIDANCE_EVENTS_RET_CACHE.exists():
        log.info("loading cached events_ret from %s", GUIDANCE_EVENTS_RET_CACHE)
        events_ret = joblib.load(GUIDANCE_EVENTS_RET_CACHE)
    else:
        events_ret = compute_event_returns(events, ohlcv_bgn, ohlcv_end)
        # add pre_ret_5d (observable sentiment proxy)
        events_ret = compute_pre_event_returns(events_ret, ohlcv_bgn, ohlcv_end)
        # add YoY OP growth (fundamental direction)
        events_ret = enrich_with_yoy_and_pre_ret(events_ret)
        joblib.dump(events_ret, GUIDANCE_EVENTS_RET_CACHE)
        log.info("cached events_ret -> %s", GUIDANCE_EVENTS_RET_CACHE)
    log.info("events with returns: %d", len(events_ret))

    n_with_growth = int(events_ret["op_growth"].notna().sum()) \
        if "op_growth" in events_ret.columns else 0
    n_with_pre_ret = int(events_ret["pre_ret_5d"].notna().sum()) \
        if "pre_ret_5d" in events_ret.columns else 0
    log.info("events with op_growth: %d / %d", n_with_growth, len(events_ret))
    log.info("events with pre_ret_5d: %d / %d", n_with_pre_ret, len(events_ret))

    # Step 3: candidate pool
    pool = candidate_pool_returns(events_ret, ohlcv_bgn, ohlcv_end)
    log.info("candidate pool: %d", len(pool))

    # Step 4a: fundamental track (direction by YoY OP growth)
    fundamental_quadrants = run_quadrant_by_yoy(events_ret, pool, "FUND")
    # Step 4b: observable track (direction by pre_ret_5d sentiment)
    observable_quadrants = run_quadrant_by_pre_ret(events_ret, pool)

    # Step 5: 5-fold TS-CV on FUND A focus
    valid = events_ret.dropna(subset=["op_growth", "fwd_ret_gross"]).copy() \
        if "op_growth" in events_ret.columns else pd.DataFrame()
    fund_pos = valid[valid["op_growth"] >= GROWTH_THRESHOLD] \
        if not valid.empty else pd.DataFrame()
    if not fund_pos.empty:
        fund_tscv = five_fold_tscv(fund_pos, pool)
    else:
        fund_tscv = {"fold_count": 0, "n_pass": 0, "pass": False, "folds": []}

    # Lesson #29 cross-proxy verdict
    fund_a = fundamental_quadrants.get("A_focus_pos_long", {}) \
        if isinstance(fundamental_quadrants, dict) else {}
    obs_a = observable_quadrants.get("A_focus_pos_long", {}) \
        if isinstance(observable_quadrants, dict) else {}
    fund_pass = bool(fund_a.get("pass_three_gate")
                     and fund_a.get("pass_concentration", False))
    obs_pass = bool(obs_a.get("pass_three_gate")
                    and obs_a.get("pass_concentration", False))
    fund_b = fundamental_quadrants.get("B_same_neg_short", {}) \
        if isinstance(fundamental_quadrants, dict) else {}
    obs_b = observable_quadrants.get("B_same_neg_short", {}) \
        if isinstance(observable_quadrants, dict) else {}

    summary = {
        "hypothesis": "H2_guidance_amend_30pct",
        "design": {
            "universe": f"top-{TOP_KOSPI} KOSPI + top-{TOP_KOSDAQ} KOSDAQ",
            "window": f"{WINDOW_BGN}..{WINDOW_END}",
            "hold_days": HOLD_DAYS,
            "fee_round_trip_bp": int(FEE_ROUND_TRIP * 10_000),
            "growth_threshold": GROWTH_THRESHOLD,
            "pre_ret_lookback_days": PRE_RET_LOOKBACK_DAYS,
            "min_cell_n": MIN_CELL_N,
            "max_symbol_fraction": MAX_SYMBOL_FRACTION,
            "tscv_min_pass": TSCV_MIN_PASS,
            "trigger": "EARNINGS_GUIDANCE_AMEND classifier (매출액또는손익구조30%이상변경)",
        },
        "totals": {
            "n_events_raw": int(len(events)),
            "n_events_with_returns": int(len(events_ret)),
            "n_with_op_growth": n_with_growth,
            "n_with_pre_ret_5d": n_with_pre_ret,
            "n_distinct_stocks": int(events["stock_code"].nunique()),
            "candidate_pool_n": int(len(pool)),
        },
        "fundamental_track_quadrants": fundamental_quadrants,
        "observable_track_quadrants": observable_quadrants,
        "fundamental_5fold_tscv": fund_tscv,
        "cross_proxy_verdict": _cross_proxy_verdict(
            fund_pass, obs_pass, fund_b, obs_b, fund_tscv
        ),
        "lesson_29_summary": {
            "rule": "Both observable (pre_ret_5d) and fundamental (YoY OP growth) tracks must independently PASS for paradigm qualification",
            "fundamental_A_focus_pass": fund_pass,
            "observable_A_focus_pass": obs_pass,
            "both_pass": fund_pass and obs_pass,
            "single_proxy_only": (fund_pass or obs_pass) and not (fund_pass and obs_pass),
        },
        "limitations": [
            "가이던스 공시는 잠정실적 직전/동시 발표 가능 → H1과 timing overlap 위험",
            "YoY OP growth direction이 가이던스 공시 본문 magnitude와 정확히 동일하지 않을 수 있음 (분기 vs 연간 cumulative)",
            "Pre_ret_5d 5d prior to event는 짧음 (가이던스 leak window는 더 길 수 있음)",
            "Trigger 자체가 ±30% magnitude 의무 공시이므로 mid_growth 거의 0 가정",
        ],
        "generated_at_utc": datetime.utcnow().isoformat(),
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
        "cross_proxy_verdict": summary["cross_proxy_verdict"],
        "n_events": int(len(events_ret)),
        "fund_pos_n": int(len(fund_pos)),
        "fund_aggregate_pass": fund_pass,
        "obs_aggregate_pass": obs_pass,
        "fund_tscv": f"{fund_tscv['n_pass']}/{fund_tscv['fold_count']}",
        "out": str(OUT_PATH),
    }, ensure_ascii=False))


def _cross_proxy_verdict(fund_pass: bool, obs_pass: bool, fund_b: dict,
                         obs_b: dict, fund_tscv: dict) -> str:
    """Lesson #29 strict verdict:
      Both A focus PASS + fund TS-CV ≥ 3/5 → PROMOTE_R2
      Single track A focus PASS → SINGLE_PROXY_TRAP (paradigm 92 동형)
      Both fail → BROAD_FALSIFIED
    """
    if fund_pass and obs_pass and fund_tscv.get("pass"):
        return "PASS_R1_CROSS_PROXY_PROMOTE_R2"
    if fund_pass and obs_pass and not fund_tscv.get("pass"):
        return "PASS_AGG_BUT_TSCV_FRAGILE"
    if fund_pass and not obs_pass:
        return "SINGLE_PROXY_TRAP_FUND_ONLY"
    if obs_pass and not fund_pass:
        return "SINGLE_PROXY_TRAP_OBS_ONLY"
    # Check B-track sanity (neg surprise SHORT)
    fund_b_pass = bool(fund_b.get("pass_three_gate") and fund_b.get("pass_concentration", False))
    obs_b_pass = bool(obs_b.get("pass_three_gate") and obs_b.get("pass_concentration", False))
    if fund_b_pass and obs_b_pass:
        return "B_SIGN_ONLY_BOTH_PROXIES"
    return "BROAD_FALSIFIED"


if __name__ == "__main__":
    main()
