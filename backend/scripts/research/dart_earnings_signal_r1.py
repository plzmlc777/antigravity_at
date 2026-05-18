"""H1 R-1 — 잠정실적 surprise momentum (Track 3 Sub-task 3B).

Hypothesis (degraded for R-1, sans 컨센서스):
  잠정실적 발표 후 시초가 gap이 surprise sign의 관측 가능한 proxy.
  Gap ≥ +X% (positive surprise proxy) → 발표 후 1d open 매수 → +5d hold.

Why proxy: true earnings surprise needs 컨센서스 estimate, which Naver covers
≈70% with paywall friction. For R-1 we substitute the *observable* gap as
surprise sign. If even this proxy fails 4-quadrant test, true-surprise H1
is unlikely to pass either. If proxy PASSES, R-2 should re-test with Naver
컨센서스 integration.

Test design (per `track3_dart_pipeline_design.md` §7.1):
  Universe: top-200 KOSPI + top-150 KOSDAQ by market cap (Naver proxy
            for KOSPI200/KOSDAQ150 since pykrx KRX endpoint requires login).
  Window:   2024-01-01 .. 2026-04-30 (2.4yr).
  Trigger:  공정공시 영업(잠정)실적 OR 연결재무제표기준영업(잠정)실적
            (subsidiary-only variants excluded).
  Entry:    next trading day open after rcept_dt.
  Exit:     +5 trading days close.
  Surprise: gap = (entry_open / prior_close − 1), thresholds tested {+/-3%}.
  Fee:      50bp round-trip (KR equity 25bp buy + 25bp sell incl. tax/spread).

4-quadrant Symmetric Negative Test (Lesson #19):
  A focus     : pos_gap × LONG  (post-positive-surprise drift)
  A mirror    : pos_gap × SHORT
  B same-sign : neg_gap × SHORT (post-negative-surprise drift)
  B mirror    : neg_gap × LONG

Lesson grid:
  #11 sample density prescreen (per-cell n ≥ 30)
  #19 4-quadrant symmetric test (auto)
  #26 small-sample Concentration Gate (per-symbol fraction)
  #27 entry-side immediate-demand (잠정실적 = entry_immediate, classified)
  #28 substrate availability (DART publishes event same day, prior close + next
       open both observable → PASS)

Output: backend/runs/dart_track/h1_earnings_r1_metrics.json
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

from app.services.dart_adapter import iter_disclosures_chunked  # noqa: E402
from app.services.disclosure_parser import is_earnings_event, is_subsidiary_only  # noqa: E402
from scripts.research._naver_kr_equity import (  # noqa: E402
    build_universe, get_ohlcv_cached, warm_cache,
)
from scripts.research._perm_utils import fee_aware_perm_test, bootstrap_ci  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("h1_r1")

# ── Config ────────────────────────────────────────────────────────────────────
TOP_KOSPI = 200
TOP_KOSDAQ = 150
WINDOW_BGN = "20240101"
WINDOW_END = "20260430"
OHLCV_PAD_DAYS = 20  # extra padding around event window for safety
HOLD_DAYS = 5         # +5 trading days close exit
FEE_ROUND_TRIP = 0.005  # 50bp KR equity round-trip
GAP_THRESHOLD = 0.03    # ±3% gap = surprise proxy
MIN_CELL_N = 30         # Lesson #11
MAX_SYMBOL_FRACTION = 0.10  # Lesson #26 Concentration Gate (one symbol ≤ 10%)
OUT_DIR = ROOT / "runs" / "dart_track"
OUT_PATH = OUT_DIR / "h1_earnings_r1_metrics.json"


def collect_events(universe_codes: set[str]) -> pd.DataFrame:
    """Sweep DART list.json over 2.4yr for KOSPI + KOSDAQ, keep 잠정실적 events
    whose stock_code ∈ universe_codes."""
    rows = []
    for corp_cls in ("Y", "K"):
        log.info("DART sweep corp_cls=%s (this may take 2-3 min × cls)", corp_cls)
        cnt_seen = cnt_kept = 0
        for r in iter_disclosures_chunked(
            bgn_de=WINDOW_BGN, end_de=WINDOW_END,
            corp_cls=corp_cls, pblntf_ty="I", chunk_days=30,
        ):
            cnt_seen += 1
            nm = r.get("report_nm", "")
            if not is_earnings_event(nm):
                continue
            if is_subsidiary_only(nm):
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
        log.info("corp_cls=%s seen=%d kept=%d", corp_cls, cnt_seen, cnt_kept)
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates(subset=["rcept_no"]).reset_index(drop=True)
        df["rcept_dt"] = pd.to_datetime(df["rcept_dt"], format="%Y%m%d")
    return df


def compute_event_returns(events: pd.DataFrame, ohlcv_bgn: str,
                          ohlcv_end: str) -> pd.DataFrame:
    """For each event, look up prior_close + entry_open + exit_close.
    Returns events DataFrame augmented with gap, fwd_ret_5d, side_long, side_short."""
    out_rows = []
    skipped = 0
    by_code = events.groupby("stock_code")
    total_codes = len(by_code)
    log.info("computing event returns across %d symbols", total_codes)
    for idx, (code, grp) in enumerate(by_code, 1):
        df = get_ohlcv_cached(code, ohlcv_bgn, ohlcv_end)
        if df.empty:
            skipped += len(grp)
            continue
        df = df.set_index("date").sort_index()
        dates_array = df.index.values  # numpy datetime64[ns]
        for _, ev in grp.iterrows():
            ev_dt = ev["rcept_dt"].to_datetime64()
            # next trading day strictly AFTER ev_dt
            pos = int(np.searchsorted(dates_array, ev_dt, side="right"))
            if pos < 1 or pos + HOLD_DAYS >= len(df):
                skipped += 1
                continue
            prior_close = float(df["close"].iloc[pos - 1])
            entry_open = float(df["open"].iloc[pos])
            exit_close = float(df["close"].iloc[pos + HOLD_DAYS - 1])  # +5d close
            if not (prior_close > 0 and entry_open > 0 and exit_close > 0):
                skipped += 1
                continue
            gap = entry_open / prior_close - 1.0
            fwd_ret = exit_close / entry_open - 1.0
            row = ev.to_dict()
            row.update({
                "entry_date": df.index[pos],
                "exit_date": df.index[pos + HOLD_DAYS - 1],
                "prior_close": prior_close,
                "entry_open": entry_open,
                "exit_close": exit_close,
                "gap": gap,
                "fwd_ret_gross": fwd_ret,
            })
            out_rows.append(row)
        if idx % 50 == 0:
            log.info("  returns %d/%d codes processed", idx, total_codes)
    log.info("event returns: kept=%d skipped=%d", len(out_rows), skipped)
    return pd.DataFrame(out_rows)


def candidate_pool_returns(events: pd.DataFrame, ohlcv_bgn: str,
                           ohlcv_end: str, sample_n: int = 12000,
                           rng_seed: int = 42) -> np.ndarray:
    """For fee_aware_perm_test, sample N random 5d-hold open-to-close returns
    across the universe (regardless of trigger). This is the null pool of
    'what if we entered at a random next-bar open'."""
    rng = np.random.default_rng(rng_seed)
    codes = events["stock_code"].unique()
    out = []
    samples_per_code = max(2, sample_n // max(1, len(codes)))
    for code in codes:
        df = get_ohlcv_cached(code, ohlcv_bgn, ohlcv_end)
        if df.empty or len(df) < HOLD_DAYS + 2:
            continue
        df = df.sort_values("date").reset_index(drop=True)
        # all valid entry indices: pos such that pos+HOLD_DAYS-1 < len(df)
        valid_idx = np.arange(0, len(df) - HOLD_DAYS)
        if len(valid_idx) == 0:
            continue
        pick = rng.choice(valid_idx, size=min(samples_per_code, len(valid_idx)),
                          replace=False)
        opens = df["open"].iloc[pick].values
        closes = df["close"].iloc[pick + HOLD_DAYS - 1].values
        mask = (opens > 0) & (closes > 0)
        out.append(closes[mask] / opens[mask] - 1.0)
    return np.concatenate(out) if out else np.array([])


def cell_stats(returns: np.ndarray, direction: int, label: str,
               by_symbol_count: dict[str, int] | None = None,
               total_symbol_trades: int = 0) -> dict:
    """Compute per-cell stats with fee subtraction and Concentration Gate."""
    n = len(returns)
    if n == 0:
        return {"label": label, "n": 0, "gross_mean_bp": None,
                "net_mean_bp": None, "t_stat": None, "concentration": None,
                "pass_n": False}
    gross = returns * direction
    net = gross - FEE_ROUND_TRIP
    t = float(net.mean() / net.std(ddof=1) * np.sqrt(n)) if n >= 2 and net.std(ddof=1) > 0 else 0.0
    cell = {
        "label": label,
        "n": int(n),
        "gross_mean_bp": float(gross.mean() * 10_000),
        "net_mean_bp": float(net.mean() * 10_000),
        "t_stat": t,
        "pass_n": n >= MIN_CELL_N,
        "fee_round_trip_bp": int(FEE_ROUND_TRIP * 10_000),
    }
    if by_symbol_count is not None and total_symbol_trades:
        top_sym, top_n = max(by_symbol_count.items(), key=lambda kv: kv[1])
        cell["concentration_top_sym"] = top_sym
        cell["concentration_top_frac"] = float(top_n / total_symbol_trades)
        cell["pass_concentration"] = (top_n / total_symbol_trades) <= MAX_SYMBOL_FRACTION
    return cell


def run_quadrant(events_ret: pd.DataFrame, pool_returns: np.ndarray) -> dict:
    """4-quadrant Symmetric Negative Test."""
    if events_ret.empty:
        return {"error": "events_ret empty"}

    pos = events_ret[events_ret["gap"] >= GAP_THRESHOLD]
    neg = events_ret[events_ret["gap"] <= -GAP_THRESHOLD]

    def per_sym_counts(df: pd.DataFrame) -> dict[str, int]:
        return df["stock_code"].value_counts().to_dict()

    quadrants = {
        "A_focus_pos_long":   {"df": pos, "dir": +1, "label": "pos_gap × LONG"},
        "A_mirror_pos_short": {"df": pos, "dir": -1, "label": "pos_gap × SHORT"},
        "B_same_neg_short":   {"df": neg, "dir": -1, "label": "neg_gap × SHORT"},
        "B_mirror_neg_long":  {"df": neg, "dir": +1, "label": "neg_gap × LONG"},
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
        # signal_t_excess via fee_aware_perm_test (signed: direction × gross + fee penalty)
        observed_net = returns * spec["dir"] - FEE_ROUND_TRIP
        perm = fee_aware_perm_test(
            observed_net_returns=observed_net.tolist(),
            candidate_pool_returns=(pool_returns * spec["dir"]).tolist(),
            fee_per_trade=FEE_ROUND_TRIP,
            n_perms=1000,
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
        # Three-gate per-cell PASS (Lesson #11 + fee-aware perm + bootstrap CI)
        passes_signal = (
            cell["pass_n"] and
            cell.get("signal_t_excess") is not None and cell["signal_t_excess"] >= 2.0 and
            cell.get("ci_lower_bp") is not None and cell["ci_lower_bp"] > 0 and
            cell.get("perm_p_one_sided_above") is not None and cell["perm_p_one_sided_above"] <= 0.10
        )
        cell["pass_three_gate"] = bool(passes_signal)
        out[key] = cell
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log.info("=== H1 R-1: 잠정실적 surprise momentum (gap proxy) ===")
    log.info("Universe: top-%d KOSPI + top-%d KOSDAQ", TOP_KOSPI, TOP_KOSDAQ)
    log.info("Window: %s .. %s, hold=%dd, fee_RT=%.1fbp, gap_thr=±%.1f%%",
             WINDOW_BGN, WINDOW_END, HOLD_DAYS, FEE_ROUND_TRIP * 10_000,
             GAP_THRESHOLD * 100)

    universe = build_universe(TOP_KOSPI, TOP_KOSDAQ)
    universe_codes = set(universe["itemCode"].astype(str).str.zfill(6).tolist())
    log.info("universe size: %d", len(universe_codes))

    events = collect_events(universe_codes)
    log.info("잠정실적 events kept: %d (across %d distinct stocks)",
             len(events), events["stock_code"].nunique() if not events.empty else 0)
    if events.empty:
        json.dump({"status": "no_events"}, OUT_PATH.open("w"))
        return

    # Warm OHLCV cache for all stocks with at least one event
    ohlcv_bgn = (pd.to_datetime(WINDOW_BGN, format="%Y%m%d")
                 - pd.Timedelta(days=OHLCV_PAD_DAYS)).strftime("%Y%m%d")
    ohlcv_end = (pd.to_datetime(WINDOW_END, format="%Y%m%d")
                 + pd.Timedelta(days=OHLCV_PAD_DAYS)).strftime("%Y%m%d")
    codes_to_fetch = sorted(events["stock_code"].unique())
    log.info("warming OHLCV cache for %d codes (~%dmin)",
             len(codes_to_fetch), len(codes_to_fetch) // 10 + 1)
    warm_cache(codes_to_fetch, ohlcv_bgn, ohlcv_end, sleep_s=0.08)

    events_ret = compute_event_returns(events, ohlcv_bgn, ohlcv_end)
    log.info("events with valid returns: %d", len(events_ret))

    pool = candidate_pool_returns(events_ret, ohlcv_bgn, ohlcv_end)
    log.info("candidate pool returns: %d", len(pool))

    quadrants = run_quadrant(events_ret, pool)

    # Lesson #11 prescreen summary
    cell_pass_n = [c["n"] for c in quadrants.values() if c.get("n", 0) > 0]
    summary = {
        "hypothesis": "H1_gap_proxy",
        "design": {
            "universe": f"top-{TOP_KOSPI} KOSPI + top-{TOP_KOSDAQ} KOSDAQ (Naver market cap proxy)",
            "window": f"{WINDOW_BGN}..{WINDOW_END}",
            "hold_days": HOLD_DAYS,
            "fee_round_trip_bp": int(FEE_ROUND_TRIP * 10_000),
            "gap_threshold": GAP_THRESHOLD,
            "min_cell_n": MIN_CELL_N,
            "max_symbol_fraction": MAX_SYMBOL_FRACTION,
            "ohlcv_source": "Naver siseJson",
            "earnings_source": "DART OpenAPI pblntf_ty=I, report_nm ∈ {잠정실적 patterns}",
        },
        "totals": {
            "n_events_raw": int(len(events)),
            "n_events_with_returns": int(len(events_ret)),
            "n_distinct_stocks_with_events": int(events["stock_code"].nunique()),
            "candidate_pool_n": int(len(pool)),
            "pos_gap_n": int(len(events_ret[events_ret["gap"] >= GAP_THRESHOLD])),
            "neg_gap_n": int(len(events_ret[events_ret["gap"] <= -GAP_THRESHOLD])),
            "mid_gap_n": int(len(events_ret[
                (events_ret["gap"] > -GAP_THRESHOLD) &
                (events_ret["gap"] < GAP_THRESHOLD)
            ])),
        },
        "lesson_11_prescreen": {
            "all_quadrants_n_min": min(cell_pass_n) if cell_pass_n else 0,
            "pass": all(c["pass_n"] for c in quadrants.values()),
        },
        "quadrants": quadrants,
        "verdict": _verdict(quadrants),
        "limitations": [
            "Gap proxy is observable surprise sign — true 컨센서스 surprise not used. ",
            "If proxy fails, true-surprise H1 unlikely to pass either. ",
            "If proxy passes, R-2 should validate with Naver 컨센서스 integration.",
            "After-hours rcept_dt approximated as 'next trading day open' (no intra-bar timestamp).",
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
    print(json.dumps({"verdict": summary["verdict"],
                      "n_events": summary["totals"]["n_events_with_returns"],
                      "out": str(OUT_PATH)}, ensure_ascii=False))


def _verdict(quadrants: dict) -> str:
    a = quadrants.get("A_focus_pos_long", {})
    b = quadrants.get("B_same_neg_short", {})
    a_pass = a.get("pass_three_gate") and a.get("pass_concentration", False)
    b_pass = b.get("pass_three_gate") and b.get("pass_concentration", False)
    if a_pass and b_pass:
        return "PASS_R1_FULL_BOTH_SIGNS"
    if a_pass and not b_pass:
        return "PASS_R1_POSITIVE_SURPRISE_ONLY"
    if b_pass and not a_pass:
        return "PASS_R1_NEGATIVE_SURPRISE_ONLY"
    # mirror sanity
    a_mirror = quadrants.get("A_mirror_pos_short", {})
    b_mirror = quadrants.get("B_mirror_neg_long", {})
    if a_mirror.get("pass_three_gate") or b_mirror.get("pass_three_gate"):
        return "FAIL_MIRROR_PASSED_SUSPICIOUS"
    return "FAIL_BROAD_FALSIFIED"


if __name__ == "__main__":
    main()
