"""R-2 expansion for paradigm `binance_delisting_announce_short_alt`.

Inherits R-1 artifacts:
  - delisting_events.csv (n=57)
  - ohlcv_cache/*.joblib  (57 syms, 1m bars covering announce-window AND post-delist window)
  - r1__metrics.json      (A focus SHORT PASS_R1_FULL, A mirror LONG FAIL)

R-2 scope (user-mandated):
  Part 1: Symmetric Negative Test 4-quadrant completion (Lesson #19)
          - A focus SHORT  (already in R-1 → re-confirm with same code path)
          - A mirror LONG  (already in R-1)
          - B same-sign LONG  (post-delist 0..+24h close, LONG)  ← NEW
          - B mirror SHORT    (post-delist 0..+24h close, SHORT) ← NEW

          Critical data check: post-delist 1m bars may be unavailable after Binance
          freezes the market. If <30 syms have ≥1h of post-delist data, fall back to
          B-restricted variant (delist−6h..delist+0).

  Part 2: Walk-forward temporal robustness (A focus SHORT only)
          - IS (first 70% by entry_ts), OOS (last 30%)
          - Three-gate per split
          - 5-fold TS-CV supplement when OOS n is small
          - Drift criterion: |OOS_mean| >= 0.5 × |IS_mean|

  Part 3: R-2 PASS criteria per variant (E-type):
          median_ret ≥ 15% AND win_rate ≥ 55% AND perm_p ≤ 0.05 AND ci_lower > 0

  Re-run 4-dim Frequency-First Gate per variant.
"""
from __future__ import annotations
import csv
import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from scripts.research._perm_utils import (  # noqa: E402
    bootstrap_ci,
    fee_aware_perm_test,
)

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
log = logging.getLogger("r2_delisting")

DIR = Path(__file__).resolve().parent
CACHE = DIR / "ohlcv_cache"
EVENTS_CSV = DIR / "delisting_events.csv"
OUT_JSON = DIR / "r2__metrics.json"

FEE_BASELINE_PER_TRADE = 0.0008
FEE_STRESS_PER_TRADE = 0.0025
ENTRY_OFFSET_MIN_A = 5
EXIT_BEFORE_DELIST_MIN_A = 24 * 60

# B variant window: post-delist 0..+24h
B_ENTRY_AT = "delist_ts"          # exact delist_ts (last tradeable moment)
B_EXIT_OFFSET_MIN = 24 * 60       # +24h after delist_ts

# Data feasibility cutoffs
MIN_POST_DELIST_HOURS = 1.0       # require ≥1h post-delist bars to consider sym
MIN_B_VARIANT_SYMS = 30           # need ≥30 syms or fall back to restricted B


def load_events() -> pd.DataFrame:
    rows = []
    with open(EVENTS_CSV) as f:
        for r in csv.DictReader(f):
            rows.append({
                "symbol": r["symbol"],
                "announce_ts": pd.Timestamp(r["announce_ts"]),
                "delist_ts": pd.Timestamp(r["delist_ts"]),
                "gap_days": float(r["gap_days"]),
            })
    df = pd.DataFrame(rows)
    for c in ("announce_ts", "delist_ts"):
        if df[c].dt.tz is None:
            df[c] = df[c].dt.tz_localize("UTC")
        else:
            df[c] = df[c].dt.tz_convert("UTC")
    return df


def load_sym_ohlcv(sym: str) -> pd.DataFrame | None:
    p = CACHE / f"{sym}.joblib"
    if not p.exists():
        return None
    df = joblib.load(p)
    if df is None or df.empty:
        return None
    return df.sort_index()


def get_close_at_or_after(df, ts):
    idx = df.index.searchsorted(ts, side="left")
    if idx >= len(df):
        return None
    return df.index[idx], float(df["close"].iloc[idx])


def get_close_at_or_before(df, ts):
    idx = df.index.searchsorted(ts, side="right") - 1
    if idx < 0:
        return None
    return df.index[idx], float(df["close"].iloc[idx])


# ============================================================================
# Part 1: compute A and B trades
# ============================================================================

def compute_trades_A(events: pd.DataFrame) -> pd.DataFrame:
    """A: announce_ts+5min → delist_ts-24h (same as R-1)."""
    out_rows = []
    for _, row in events.iterrows():
        sym = row["symbol"]
        ann = row["announce_ts"]
        de = row["delist_ts"]
        entry_target = ann + pd.Timedelta(minutes=ENTRY_OFFSET_MIN_A)
        exit_target = de - pd.Timedelta(minutes=EXIT_BEFORE_DELIST_MIN_A)
        if exit_target <= entry_target:
            continue
        df = load_sym_ohlcv(sym)
        if df is None:
            continue
        e = get_close_at_or_after(df, entry_target)
        x = get_close_at_or_before(df, exit_target)
        if e is None or x is None:
            continue
        entry_ts, entry_px = e
        exit_ts, exit_px = x
        if exit_ts <= entry_ts:
            continue
        hold_days = (exit_ts - entry_ts).total_seconds() / 86400.0
        long_gross = (exit_px / entry_px) - 1.0
        out_rows.append({
            "symbol": sym, "announce_ts": ann, "delist_ts": de,
            "entry_ts": entry_ts, "exit_ts": exit_ts, "hold_days": hold_days,
            "entry_px": entry_px, "exit_px": exit_px,
            "long_gross": long_gross, "short_gross": -long_gross,
            "quarter": pd.Timestamp(ann).to_period("Q").strftime("%Y-Q%q"),
            "variant": "A",
        })
    return pd.DataFrame(out_rows)


def assess_b_data_feasibility(events: pd.DataFrame) -> dict:
    """Per-sym post-delist data audit."""
    rows = []
    for _, row in events.iterrows():
        sym = row["symbol"]
        de = row["delist_ts"]
        df = load_sym_ohlcv(sym)
        if df is None:
            rows.append({"symbol": sym, "delist_ts": de, "has_data": False,
                         "post_delist_bars": 0, "post_delist_hours": 0.0})
            continue
        # Count bars at or after delist_ts (use index AFTER delist_ts)
        idx = df.index.searchsorted(de, side="left")
        post = df.iloc[idx:]
        post_bars = len(post)
        post_hours = post_bars / 60.0  # 1m bars
        # also note last bar timestamp
        last_ts = df.index.max()
        rows.append({
            "symbol": sym,
            "delist_ts": str(de),
            "last_cached_bar": str(last_ts),
            "has_data": post_bars > 0,
            "post_delist_bars": int(post_bars),
            "post_delist_hours": float(post_hours),
            "meets_1h_cutoff": post_hours >= MIN_POST_DELIST_HOURS,
        })
    df = pd.DataFrame(rows)
    n_with_1h = int(df["meets_1h_cutoff"].sum())
    return {
        "n_total_events": int(len(df)),
        "n_with_post_delist_data": int(df["has_data"].sum()),
        "n_meeting_1h_cutoff": n_with_1h,
        "min_b_syms_cutoff": MIN_B_VARIANT_SYMS,
        "feasible_for_full_24h_b": n_with_1h >= MIN_B_VARIANT_SYMS,
        "per_event_audit": df.to_dict(orient="records"),
    }


def compute_trades_B(events: pd.DataFrame, restricted: bool = False) -> pd.DataFrame:
    """B same-sign / mirror: post-delist 24h window.
    If restricted=True, fall back to (delist-6h..delist+0) instead.
    """
    out_rows = []
    for _, row in events.iterrows():
        sym = row["symbol"]
        ann = row["announce_ts"]
        de = row["delist_ts"]
        if restricted:
            entry_target = de - pd.Timedelta(hours=6)
            exit_target = de
        else:
            entry_target = de
            exit_target = de + pd.Timedelta(minutes=B_EXIT_OFFSET_MIN)
        df = load_sym_ohlcv(sym)
        if df is None:
            continue
        e = get_close_at_or_after(df, entry_target)
        x = get_close_at_or_before(df, exit_target)
        if e is None or x is None:
            continue
        entry_ts, entry_px = e
        exit_ts, exit_px = x
        if exit_ts <= entry_ts:
            continue
        hold_days = (exit_ts - entry_ts).total_seconds() / 86400.0
        long_gross = (exit_px / entry_px) - 1.0
        out_rows.append({
            "symbol": sym, "announce_ts": ann, "delist_ts": de,
            "entry_ts": entry_ts, "exit_ts": exit_ts, "hold_days": hold_days,
            "entry_px": entry_px, "exit_px": exit_px,
            "long_gross": long_gross, "short_gross": -long_gross,
            "quarter": pd.Timestamp(ann).to_period("Q").strftime("%Y-Q%q"),
            "variant": "B_restricted" if restricted else "B",
        })
    return pd.DataFrame(out_rows)


def build_candidate_pool(trades_df: pd.DataFrame) -> dict[str, np.ndarray]:
    """Same as R-1: random non-overlapping windows of same hold-duration."""
    long_pool = []
    short_pool = []
    for _, row in trades_df.iterrows():
        sym = row["symbol"]
        hold_days = row["hold_days"]
        df = load_sym_ohlcv(sym)
        if df is None:
            continue
        hold_bars = int(hold_days * 1440)
        if hold_bars < 5:
            continue
        stride = max(1, hold_bars // 3)
        for i in range(0, len(df) - hold_bars, stride):
            entry_px = float(df["close"].iloc[i])
            exit_px = float(df["close"].iloc[i + hold_bars])
            if entry_px <= 0 or exit_px <= 0:
                continue
            r = exit_px / entry_px - 1.0
            long_pool.append(r)
            short_pool.append(-r)
    return {
        "long": np.array(long_pool, dtype=float),
        "short": np.array(short_pool, dtype=float),
    }


# ============================================================================
# Stat utilities (mirror R-1)
# ============================================================================

def three_gate(observed_gross: np.ndarray, candidate_pool: np.ndarray,
               fee: float, label: str) -> dict:
    obs_net = observed_gross - fee
    fee_res = fee_aware_perm_test(
        observed_net_returns=obs_net,
        candidate_pool_returns=candidate_pool,
        fee_per_trade=fee,
        n_perms=1000,
    )
    ci_res = bootstrap_ci(obs_net, n_boot=2000, block_size=1)
    gate = {
        "label": label,
        "fee_per_trade": fee,
        "n_obs": int(len(obs_net)),
        "obs_mean_bp": float(obs_net.mean() * 10000) if len(obs_net) else float("nan"),
        "obs_median_bp": float(np.median(obs_net) * 10000) if len(obs_net) else float("nan"),
        "obs_win_rate": float((obs_net > 0).mean()) if len(obs_net) else float("nan"),
        "obs_t": fee_res.get("obs_t", float("nan")),
        "null_mean_t": fee_res.get("null_mean_t", float("nan")),
        "signal_t_excess": fee_res.get("signal_t_excess", float("nan")),
        "perm_p_two_sided": fee_res.get("perm_p_two_sided", float("nan")),
        "perm_p_one_sided_above": fee_res.get("perm_p_one_sided_above", float("nan")),
        "perm_p_one_sided_below": fee_res.get("perm_p_one_sided_below", float("nan")),
        "ci_lower_bp": (ci_res.get("ci_lower", float("nan")) * 10000) if not math.isnan(ci_res.get("ci_lower", float("nan"))) else float("nan"),
        "ci_upper_bp": (ci_res.get("ci_upper", float("nan")) * 10000) if not math.isnan(ci_res.get("ci_upper", float("nan"))) else float("nan"),
        "prob_positive": ci_res.get("prob_positive", float("nan")),
        "n_candidate_pool": int(len(candidate_pool)),
    }
    sig_ex = gate["signal_t_excess"]
    ci_lo = gate["ci_lower_bp"]
    pp = gate["perm_p_two_sided"]
    gate["gate_a_sigex_pass"] = (not math.isnan(sig_ex)) and sig_ex >= 2.0
    gate["gate_b_ci_pass"] = (not math.isnan(ci_lo)) and ci_lo > 0
    gate["gate_c_perm_p_pass"] = (not math.isnan(pp)) and pp <= 0.10
    gate["three_gate_pass"] = (gate["gate_a_sigex_pass"] and gate["gate_b_ci_pass"]
                               and gate["gate_c_perm_p_pass"])
    return gate


def r2_etype_pass(gate_baseline: dict) -> dict:
    """R-2 PASS criteria (E-type):
       median_ret >= 15% AND win_rate >= 55% AND perm_p <= 0.05 AND ci_lower > 0
    """
    median_bp = gate_baseline.get("obs_median_bp", float("nan"))
    win_rate = gate_baseline.get("obs_win_rate", float("nan"))
    perm_p = gate_baseline.get("perm_p_two_sided", float("nan"))
    ci_lo = gate_baseline.get("ci_lower_bp", float("nan"))
    median_pct = median_bp / 100.0   # bp → %
    g_med = (not math.isnan(median_pct)) and median_pct >= 15.0
    g_win = (not math.isnan(win_rate)) and win_rate >= 0.55
    g_perm = (not math.isnan(perm_p)) and perm_p <= 0.05
    g_ci = (not math.isnan(ci_lo)) and ci_lo > 0
    fails = []
    if not g_med:
        fails.append(f"median_pct={median_pct:.2f}<15")
    if not g_win:
        fails.append(f"win_rate={win_rate:.3f}<0.55")
    if not g_perm:
        fails.append(f"perm_p={perm_p:.4f}>0.05")
    if not g_ci:
        fails.append(f"ci_lower_bp={ci_lo:.2f}<=0")
    return {
        "median_pct": median_pct,
        "win_rate": win_rate,
        "perm_p": perm_p,
        "ci_lower_bp": ci_lo,
        "median_pass": bool(g_med),
        "win_rate_pass": bool(g_win),
        "perm_p_pass": bool(g_perm),
        "ci_pass": bool(g_ci),
        "etype_pass": bool(g_med and g_win and g_perm and g_ci),
        "fail_dims": fails,
    }


def concentration(trades_df: pd.DataFrame, side: str, fee: float) -> dict:
    col = f"{side}_gross"
    df = trades_df.copy()
    df["net"] = df[col] - fee
    per_q = df.groupby("quarter").agg(
        n_trades=("net", "size"),
        mean_bp=("net", lambda s: float(s.mean()) * 10000),
        t_stat=("net", lambda s: float(s.mean() / s.std(ddof=1) * (len(s) ** 0.5))
                if len(s) >= 3 and s.std(ddof=1) > 0 else float("nan")),
    ).reset_index()
    per_q_records = per_q.to_dict(orient="records")
    n_q_measurable = int((per_q["n_trades"] >= 10).sum())
    pos_q = per_q[(per_q["n_trades"] >= 10) & (per_q["t_stat"] > 0)]
    n_q_pos_t = int(len(pos_q))
    quarter_pos_t_ratio = (n_q_pos_t / n_q_measurable) if n_q_measurable else float("nan")

    n_total = len(df)
    if n_total == 0:
        top3_pct = float("nan")
    else:
        sorted_net = df["net"].abs().sort_values(ascending=False)
        top3 = float(sorted_net.head(3).sum())
        all_sum = float(sorted_net.sum())
        top3_pct = (top3 / all_sum * 100.0) if all_sum > 0 else float("nan")

    n_pos = int((df["net"] > 0).sum())
    n_neg = int((df["net"] < 0).sum())
    sign_ratio = n_pos / n_total if n_total else float("nan")
    quarter_pass = (not math.isnan(quarter_pos_t_ratio)) and quarter_pos_t_ratio >= 0.5
    sign_pass = (not math.isnan(sign_ratio)) and sign_ratio >= 0.50
    blowup_pass = (not math.isnan(top3_pct)) and top3_pct < 40.0
    return {
        "side": side,
        "per_quarter_t_stats": per_q_records,
        "n_quarters_measurable": n_q_measurable,
        "n_quarters_pos_t": n_q_pos_t,
        "quarter_pos_t_ratio": quarter_pos_t_ratio,
        "n_pos": n_pos, "n_neg": n_neg, "sign_ratio_positive": sign_ratio,
        "top3_abs_concentration_pct": top3_pct,
        "concentration_gate": {
            "quarter_pass": bool(quarter_pass),
            "sign_pass": bool(sign_pass),
            "blowup_pass": bool(blowup_pass),
            "overall_pass": bool(quarter_pass and sign_pass and blowup_pass),
        },
    }


def frequency_first_gate(trades_df: pd.DataFrame, side: str, fee: float) -> dict:
    col = f"{side}_gross"
    df = trades_df.copy()
    df["net"] = df[col] - fee
    if df.empty:
        return {"side": side, "error": "empty"}
    earliest = df["entry_ts"].min()
    latest = df["exit_ts"].max()
    oos_days = (latest - earliest).total_seconds() / 86400.0
    n_events = len(df)
    trades_per_year = n_events / (oos_days / 365.0) if oos_days > 0 else float("nan")
    per_trade_net = df["net"].values
    per_trade_net_edge_pct = float(np.median(per_trade_net)) * 100.0
    mean_hold_days = float(df["hold_days"].mean())
    cap_util_pct = (mean_hold_days * n_events) / oos_days * 100.0 if oos_days > 0 else float("nan")
    mean_ret = float(per_trade_net.mean())
    std_ret = float(per_trade_net.std(ddof=1)) if n_events >= 2 else float("nan")
    if std_ret and std_ret > 0 and mean_hold_days > 0:
        single_trade_sharpe_annualized = mean_ret / std_ret * math.sqrt(365.0 / mean_hold_days)
    else:
        single_trade_sharpe_annualized = float("nan")
    cutoff_trades = 12
    cutoff_edge = 2.0
    cutoff_util = 30.0
    cutoff_sharpe = 1.5
    fail_dims = []
    if math.isnan(trades_per_year) or trades_per_year < cutoff_trades:
        fail_dims.append(f"trades_per_year={trades_per_year:.2f}<{cutoff_trades}")
    if per_trade_net_edge_pct < cutoff_edge:
        fail_dims.append(f"per_trade_net_edge_pct={per_trade_net_edge_pct:.2f}<{cutoff_edge}")
    if math.isnan(cap_util_pct) or cap_util_pct < cutoff_util:
        fail_dims.append(f"capital_utilization_pct={cap_util_pct:.2f}<{cutoff_util}")
    if math.isnan(single_trade_sharpe_annualized) or single_trade_sharpe_annualized < cutoff_sharpe:
        fail_dims.append(f"single_trade_sharpe={single_trade_sharpe_annualized:.2f}<{cutoff_sharpe}")
    verdict = "PASS" if not fail_dims else "FAIL"
    return {
        "side": side, "fee_per_trade": fee, "oos_days": oos_days, "n_events": n_events,
        "trades_per_year": trades_per_year, "per_trade_net_edge_pct": per_trade_net_edge_pct,
        "capital_utilization_pct": cap_util_pct, "mean_hold_days": mean_hold_days,
        "single_trade_sharpe_annualized": single_trade_sharpe_annualized,
        "cutoffs": {"trades_per_year": cutoff_trades, "per_trade_net_edge_pct": cutoff_edge,
                    "capital_utilization_pct": cutoff_util, "single_trade_sharpe": cutoff_sharpe},
        "gate_verdict": verdict, "fail_dims": fail_dims,
    }


# ============================================================================
# Part 2: Walk-forward (A focus SHORT)
# ============================================================================

def walk_forward(trades_a: pd.DataFrame, pool: dict, fee: float) -> dict:
    """Chronological 70/30 split + 5-fold TS-CV."""
    if trades_a.empty:
        return {"error": "empty"}
    df = trades_a.sort_values("entry_ts").reset_index(drop=True)
    n = len(df)
    split = int(round(n * 0.7))
    is_df = df.iloc[:split].copy()
    oos_df = df.iloc[split:].copy()
    log.info("walk-forward 70/30 split: IS n=%d, OOS n=%d", len(is_df), len(oos_df))

    is_short = is_df["short_gross"].values
    oos_short = oos_df["short_gross"].values

    is_gate = three_gate(is_short, pool["short"], fee, "WF_IS_SHORT_baseline")
    oos_gate = three_gate(oos_short, pool["short"], fee, "WF_OOS_SHORT_baseline")

    is_mean = is_gate["obs_mean_bp"]
    oos_mean = oos_gate["obs_mean_bp"]
    drift_ratio = (abs(oos_mean) / abs(is_mean)) if is_mean else float("nan")
    drift_pass = (not math.isnan(drift_ratio)) and drift_ratio >= 0.5
    oos_three_gate_pass = oos_gate["three_gate_pass"]
    wf_pass = is_gate["three_gate_pass"] and oos_three_gate_pass and drift_pass

    # 5-fold TS-CV (chronological folds)
    folds = []
    fold_size = max(1, n // 5)
    fold_pass_count = 0
    for k in range(5):
        lo = k * fold_size
        hi = (k + 1) * fold_size if k < 4 else n
        fold_df = df.iloc[lo:hi]
        if len(fold_df) < 5:
            folds.append({"k": k, "n": int(len(fold_df)), "skip": "n<5"})
            continue
        obs = fold_df["short_gross"].values
        g = three_gate(obs, pool["short"], fee, f"WF_CV_fold{k}_SHORT")
        folds.append({
            "k": k, "n": int(len(fold_df)),
            "mean_bp": g["obs_mean_bp"], "obs_t": g["obs_t"],
            "signal_t_excess": g["signal_t_excess"], "ci_lower_bp": g["ci_lower_bp"],
            "perm_p": g["perm_p_two_sided"], "three_gate_pass": g["three_gate_pass"],
        })
        if g["three_gate_pass"]:
            fold_pass_count += 1
    return {
        "split_70_30": {
            "n_is": int(len(is_df)), "n_oos": int(len(oos_df)),
            "is_gate": is_gate, "oos_gate": oos_gate,
            "is_mean_bp": is_mean, "oos_mean_bp": oos_mean,
            "drift_ratio_oos_over_is": drift_ratio, "drift_pass": bool(drift_pass),
            "is_three_gate_pass": is_gate["three_gate_pass"],
            "oos_three_gate_pass": bool(oos_three_gate_pass),
            "walk_forward_pass": bool(wf_pass),
        },
        "ts_cv_5fold": {
            "folds": folds,
            "fold_pass_count": int(fold_pass_count),
            "fold_total_measurable": int(sum(1 for f in folds if "skip" not in f)),
        },
    }


# ============================================================================
# Main
# ============================================================================

def main():
    log.info("== R-2 binance_delisting_announce_short_alt ==")
    events = load_events()
    log.info("events loaded: %d", len(events))

    # --- A trades (same as R-1, recompute for self-contained metrics) ---
    trades_a = compute_trades_A(events)
    log.info("A trades: %d valid", len(trades_a))
    pool_a = build_candidate_pool(trades_a)
    log.info("A candidate pool: long n=%d, short n=%d", len(pool_a["long"]), len(pool_a["short"]))

    # --- B data feasibility audit ---
    log.info("--- B variant data feasibility audit ---")
    b_feas = assess_b_data_feasibility(events)
    log.info("B feasibility: %d events have post-delist data, %d meet 1h cutoff",
             b_feas["n_with_post_delist_data"], b_feas["n_meeting_1h_cutoff"])

    # --- B trades (24h or restricted) ---
    b_window_mode = "full_24h"
    if not b_feas["feasible_for_full_24h_b"]:
        log.warning("B 24h infeasible (%d < %d) — falling back to B_restricted (delist-6h..delist+0)",
                    b_feas["n_meeting_1h_cutoff"], MIN_B_VARIANT_SYMS)
        b_window_mode = "restricted_minus6h_to_0"
        trades_b = compute_trades_B(events, restricted=True)
    else:
        trades_b = compute_trades_B(events, restricted=False)
    log.info("B trades (%s): %d valid", b_window_mode, len(trades_b))

    pool_b = build_candidate_pool(trades_b) if not trades_b.empty else {"long": np.array([]), "short": np.array([])}
    log.info("B candidate pool: long n=%d, short n=%d", len(pool_b["long"]), len(pool_b["short"]))

    # ====================================================================
    # Metrics assembly
    # ====================================================================
    metrics: dict = {
        "paradigm_name": "binance_delisting_announce_short_alt",
        "phase": "R-2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_events_loaded": int(len(events)),
        "n_trades_A": int(len(trades_a)),
        "n_trades_B": int(len(trades_b)),
        "b_window_mode": b_window_mode,
        "b_data_feasibility": b_feas,
        "fee_baseline_per_trade": FEE_BASELINE_PER_TRADE,
        "fee_stress_per_trade": FEE_STRESS_PER_TRADE,
        "config": {
            "A_entry_offset_min": ENTRY_OFFSET_MIN_A,
            "A_exit_before_delist_min": EXIT_BEFORE_DELIST_MIN_A,
            "B_exit_offset_min": B_EXIT_OFFSET_MIN,
            "B_restricted_window": "delist-6h..delist+0" if b_window_mode == "restricted_minus6h_to_0" else "N/A",
            "min_post_delist_hours": MIN_POST_DELIST_HOURS,
            "min_b_variant_syms": MIN_B_VARIANT_SYMS,
        },
    }

    # --- 4-quadrant Symmetric Negative Test ---
    metrics["symmetric_variants"] = {}

    # A focus SHORT, A mirror LONG
    for label, side, trades_src, pool_src in [
        ("A_focus_SHORT", "short", trades_a, pool_a),
        ("A_mirror_LONG", "long", trades_a, pool_a),
    ]:
        log.info("--- %s ---", label)
        observed = trades_src[f"{side}_gross"].values
        baseline = three_gate(observed, pool_src[side], FEE_BASELINE_PER_TRADE, f"{label}_fee_baseline")
        stress = three_gate(observed, pool_src[side], FEE_STRESS_PER_TRADE, f"{label}_fee_stress")
        conc = concentration(trades_src, side, FEE_BASELINE_PER_TRADE)
        freq_b = frequency_first_gate(trades_src, side, FEE_BASELINE_PER_TRADE)
        freq_s = frequency_first_gate(trades_src, side, FEE_STRESS_PER_TRADE)
        etype = r2_etype_pass(baseline)

        if baseline["three_gate_pass"] and stress["three_gate_pass"]:
            tg_v = "PASS_both_fee_levels"
        elif baseline["three_gate_pass"]:
            tg_v = "FRAGILE_PASS_FEE_SENSITIVE"
        else:
            tg_v = "FAIL"

        metrics["symmetric_variants"][label] = {
            "side": side,
            "n_obs": int(len(observed)),
            "fee_baseline": baseline, "fee_stress": stress,
            "concentration_baseline": conc,
            "frequency_first_gate_baseline": freq_b,
            "frequency_first_gate_stress": freq_s,
            "etype_r2_pass": etype,
            "three_gate_verdict": tg_v,
            "concentration_gate_overall_pass": conc["concentration_gate"]["overall_pass"],
            "frequency_gate_baseline_verdict": freq_b["gate_verdict"],
            "frequency_gate_stress_verdict": freq_s["gate_verdict"],
        }
        log.info("  three_gate=%s, etype_pass=%s, conc=%s, freq_baseline=%s",
                 tg_v, etype["etype_pass"],
                 conc["concentration_gate"]["overall_pass"], freq_b["gate_verdict"])
        log.info("  baseline: obs_t=%.3f sigex=%.3f ci=[%.1f,%.1f]bp perm_p=%.4f median=%.1fbp win=%.3f",
                 baseline["obs_t"], baseline["signal_t_excess"],
                 baseline["ci_lower_bp"], baseline["ci_upper_bp"], baseline["perm_p_two_sided"],
                 baseline["obs_median_bp"], baseline["obs_win_rate"])

    # B same-sign LONG, B mirror SHORT
    if not trades_b.empty and len(pool_b["long"]) > 10:
        for label, side in [("B_same_sign_LONG", "long"), ("B_mirror_SHORT", "short")]:
            log.info("--- %s (%s) ---", label, b_window_mode)
            observed = trades_b[f"{side}_gross"].values
            baseline = three_gate(observed, pool_b[side], FEE_BASELINE_PER_TRADE, f"{label}_fee_baseline")
            stress = three_gate(observed, pool_b[side], FEE_STRESS_PER_TRADE, f"{label}_fee_stress")
            conc = concentration(trades_b, side, FEE_BASELINE_PER_TRADE)
            freq_b_ = frequency_first_gate(trades_b, side, FEE_BASELINE_PER_TRADE)
            freq_s_ = frequency_first_gate(trades_b, side, FEE_STRESS_PER_TRADE)
            etype = r2_etype_pass(baseline)

            if baseline["three_gate_pass"] and stress["three_gate_pass"]:
                tg_v = "PASS_both_fee_levels"
            elif baseline["three_gate_pass"]:
                tg_v = "FRAGILE_PASS_FEE_SENSITIVE"
            else:
                tg_v = "FAIL"

            metrics["symmetric_variants"][label] = {
                "side": side,
                "window_mode": b_window_mode,
                "n_obs": int(len(observed)),
                "fee_baseline": baseline, "fee_stress": stress,
                "concentration_baseline": conc,
                "frequency_first_gate_baseline": freq_b_,
                "frequency_first_gate_stress": freq_s_,
                "etype_r2_pass": etype,
                "three_gate_verdict": tg_v,
                "concentration_gate_overall_pass": conc["concentration_gate"]["overall_pass"],
                "frequency_gate_baseline_verdict": freq_b_["gate_verdict"],
                "frequency_gate_stress_verdict": freq_s_["gate_verdict"],
            }
            log.info("  three_gate=%s, etype_pass=%s, conc=%s, freq_baseline=%s",
                     tg_v, etype["etype_pass"],
                     conc["concentration_gate"]["overall_pass"], freq_b_["gate_verdict"])
            log.info("  baseline: obs_t=%.3f sigex=%.3f ci=[%.1f,%.1f]bp perm_p=%.4f median=%.1fbp win=%.3f",
                     baseline["obs_t"], baseline["signal_t_excess"],
                     baseline["ci_lower_bp"], baseline["ci_upper_bp"], baseline["perm_p_two_sided"],
                     baseline["obs_median_bp"], baseline["obs_win_rate"])
    else:
        metrics["symmetric_variants"]["B_same_sign_LONG"] = {
            "error": "skipped",
            "reason": f"trades_b empty or pool too small (n_trades={len(trades_b)}, pool_long={len(pool_b.get('long', []))})",
        }
        metrics["symmetric_variants"]["B_mirror_SHORT"] = {
            "error": "skipped",
            "reason": f"trades_b empty or pool too small (n_trades={len(trades_b)}, pool_long={len(pool_b.get('long', []))})",
        }

    # --- Walk-forward (A focus SHORT) ---
    log.info("--- Walk-forward A focus SHORT ---")
    wf = walk_forward(trades_a, pool_a, FEE_BASELINE_PER_TRADE)
    metrics["walk_forward_A_focus_SHORT"] = wf
    if "split_70_30" in wf:
        s = wf["split_70_30"]
        log.info("  IS: n=%d mean=%.1fbp three_gate=%s | OOS: n=%d mean=%.1fbp three_gate=%s | drift=%.2f pass=%s",
                 s["n_is"], s["is_mean_bp"], s["is_three_gate_pass"],
                 s["n_oos"], s["oos_mean_bp"], s["oos_three_gate_pass"],
                 s["drift_ratio_oos_over_is"], s["drift_pass"])
        log.info("  WALK-FORWARD overall pass: %s", s["walk_forward_pass"])
    if "ts_cv_5fold" in wf:
        c = wf["ts_cv_5fold"]
        log.info("  5-fold TS-CV: %d / %d folds three-gate PASS",
                 c["fold_pass_count"], c["fold_total_measurable"])

    # ====================================================================
    # Overall R-2 verdict
    # ====================================================================
    a_focus = metrics["symmetric_variants"]["A_focus_SHORT"]
    a_mirror = metrics["symmetric_variants"]["A_mirror_LONG"]
    b_same = metrics["symmetric_variants"].get("B_same_sign_LONG", {})
    b_mirror = metrics["symmetric_variants"].get("B_mirror_SHORT", {})

    a_focus_3g = a_focus.get("fee_baseline", {}).get("three_gate_pass", False)
    a_focus_etype = a_focus.get("etype_r2_pass", {}).get("etype_pass", False)
    a_focus_stress = a_focus.get("fee_stress", {}).get("three_gate_pass", False)
    wf_pass = wf.get("split_70_30", {}).get("walk_forward_pass", False)
    b_same_3g = b_same.get("fee_baseline", {}).get("three_gate_pass", False) if "fee_baseline" in b_same else False

    # SPLIT_PARADIGM: B same-sign LONG PASSes 3-gate (different direction than A SHORT)
    if b_same_3g:
        overall = "SPLIT_PARADIGM_B_LONG_ALSO_PASS"
    elif a_focus_3g and not a_focus_stress:
        overall = "FRAGILE_FEE_STRESS_FAIL"
    elif a_focus_3g and not wf_pass:
        overall = "FRAGILE_TEMPORAL_WF_FAIL"
    elif a_focus_3g and wf_pass and a_focus_etype and a_focus_stress:
        overall = "PASS_R2_FULL"
    elif a_focus_3g and wf_pass and not a_focus_etype:
        overall = "PASS_R2_NARROW_ETYPE_MARGINAL"
    elif a_focus_3g:
        overall = "PASS_R2_THREE_GATE_ONLY"
    else:
        overall = "FAIL_A_FOCUS_LOST_IN_R2"
    metrics["overall_r2_verdict"] = overall

    OUT_JSON.write_text(json.dumps(metrics, default=str, indent=2))
    log.info("wrote %s", OUT_JSON)
    log.info("=== OVERALL R-2 VERDICT: %s ===", overall)


if __name__ == "__main__":
    main()
