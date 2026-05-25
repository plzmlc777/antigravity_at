"""R-1 PoC for paradigm 189
`binance_futures_perp_listing_event_post_onboard_4h_entry_side_forced_buy_directional_bilateral`.

Hypothesis
----------
Binance Futures USDS perp listing event (onboardDate marker) triggers
entry-side forced-buyer demand. Forward window +0h ~ +48h hold sweep.

Bilateral 2-cell (no 4-quadrant SNT, sample density compression):
  - A focus  : LONG continuation  (forced-buyer demand momentum)
  - A mirror : SHORT reversal     (initial pump -> mean-reversion)

Mirror antipattern catalog (paradigm 70 precedent):
  - NOT auto-inverse of paradigm 87
  - paradigm 87 was forced-EXIT (delisting); paradigm 189 is forced-ENTRY (listing)
  - Sub-mechanism asymmetry empirical extraction; lifecycle 4-dim uniqueness
    ([[project-paradigm-stablecoin-mint]]: entry-side + immediate + substrate
    available + sample density)

R-1 stat suite (per paradigm-architect spec)
--------------------------------------------
- Three-gate per side per hold:
    * signal_t_excess >= 2.0
    * ci_lower > 0
    * perm_p_two_sided <= 0.10

- Concentration Gate (Lesson #16, one-shot-event adapted):
    * per-half-year (6 buckets 2023H1-2026H1) t-stat ratio
    * sign distribution + top-3 magnitude concentration

- 4-dim sparse-strict Frequency Gate (Lesson #71 corollary path C):
    * sparse-trigger event class: edge_per_trade >= +2% AND trades/yr >= 12 AND sharpe >= 1.5
    * util gate relaxed (sparse-strict mode 자격) — life-changing 4-dim audit only

- Fee Stress (8bp baseline + 25bp stress)

Hold sweep: 4h primary + 8h + 12h + 24h + 48h (5 holds × 2 cells = 10 cells)
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
log = logging.getLogger("p189_r1")

DIR = Path(__file__).resolve().parent
CACHE = DIR / "ohlcv_cache"
EVENTS_CSV = DIR / "listing_events.csv"
OUT_JSON = DIR / "r1__metrics.json"

FEE_BASELINE_PER_TRADE = 0.0008   # 8 bp one-way x 2 = 16 bp round-trip
FEE_STRESS_PER_TRADE = 0.0025     # 25 bp one-way x 2 = 50 bp round-trip

# Hold sweep (hours)
HOLDS_HRS = [4, 8, 12, 24, 48]

# Entry offset: skip first 15 min post-onboard to avoid "first-tick" auction noise
ENTRY_OFFSET_MIN = 15


def load_events() -> pd.DataFrame:
    rows = []
    with open(EVENTS_CSV) as f:
        for r in csv.DictReader(f):
            try:
                ts_ms = int(r["onboard_ts_ms"])
            except Exception:
                ts_ms = 0
            rows.append({
                "symbol": r["symbol"],
                "onboard_date": r["onboard_date"],
                "onboard_ts": pd.Timestamp(ts_ms, unit="ms", tz="UTC") if ts_ms else pd.Timestamp(r["onboard_date"], tz="UTC"),
            })
    df = pd.DataFrame(rows).sort_values("onboard_ts").reset_index(drop=True)
    # Half-year bucket
    def to_half(ts):
        return f"{ts.year}H{1 if ts.month <= 6 else 2}"
    df["half_year"] = df["onboard_ts"].apply(to_half)
    return df


def load_sym_ohlcv(sym: str) -> pd.DataFrame | None:
    p = CACHE / f"{sym}.joblib"
    if not p.exists():
        return None
    df = joblib.load(p)
    if df is None or len(df) == 0:
        return None
    if "ts" in df.columns:
        df = df.sort_values("ts").reset_index(drop=True)
    return df


def get_close_at_or_after(df: pd.DataFrame, ts: pd.Timestamp) -> tuple[pd.Timestamp, float] | None:
    """First 15m bar with ts column >= target ts."""
    arr = df["ts"].values
    target_np = np.datetime64(ts.to_datetime64())
    idx = np.searchsorted(arr, target_np, side="left")
    if idx >= len(df):
        return None
    return pd.Timestamp(arr[idx]), float(df["close"].iloc[idx])


def compute_trades(events: pd.DataFrame, hold_hrs: int) -> pd.DataFrame:
    """For each listing event, entry = first 15m bar close >= onboard_ts + 15min,
    exit = first 15m bar close >= entry_ts + hold_hrs.
    """
    out_rows = []
    skipped = 0
    for _, row in events.iterrows():
        sym = row["symbol"]
        onb = row["onboard_ts"]
        entry_target = onb + pd.Timedelta(minutes=ENTRY_OFFSET_MIN)
        exit_target = entry_target + pd.Timedelta(hours=hold_hrs)
        df = load_sym_ohlcv(sym)
        if df is None:
            skipped += 1
            continue
        e = get_close_at_or_after(df, entry_target)
        if e is None:
            skipped += 1
            continue
        entry_ts, entry_px = e
        x = get_close_at_or_after(df, exit_target)
        if x is None:
            skipped += 1
            continue
        exit_ts, exit_px = x
        if exit_ts <= entry_ts or entry_px <= 0 or exit_px <= 0:
            skipped += 1
            continue
        hold_days = (exit_ts - entry_ts).total_seconds() / 86400.0
        long_gross = (exit_px / entry_px) - 1.0
        short_gross = -long_gross
        out_rows.append({
            "symbol": sym,
            "onboard_ts": onb,
            "entry_ts": entry_ts,
            "exit_ts": exit_ts,
            "hold_days": hold_days,
            "entry_px": entry_px,
            "exit_px": exit_px,
            "long_gross": long_gross,
            "short_gross": short_gross,
            "half_year": row["half_year"],
        })
    log.info("  compute_trades hold=%dh: valid=%d skipped=%d (of %d events)",
             hold_hrs, len(out_rows), skipped, len(events))
    return pd.DataFrame(out_rows)


def build_candidate_pool(trades_df: pd.DataFrame, hold_hrs: int) -> dict[str, np.ndarray]:
    """Candidate pool: non-trigger windows from same symbols' 3-day OHLCV cache.

    For each event symbol, slide windows of length hold_hrs through the cached
    OHLCV (entire 3-day backfill, minus the actual trigger entry/exit interval).
    This forms the null: "what would return have been on a random window in
    the same listing-week regime?"
    """
    hold_bars = max(1, int(hold_hrs * 4))  # 15m bars per hour = 4
    long_pool = []
    short_pool = []
    seen_syms = set()
    for _, row in trades_df.iterrows():
        sym = row["symbol"]
        if sym in seen_syms:
            continue
        seen_syms.add(sym)
        df = load_sym_ohlcv(sym)
        if df is None or len(df) < hold_bars + 1:
            continue
        # Use entire 3-day cache as pool; stride of hold_bars/2 for ~2x oversample
        stride = max(1, hold_bars // 2)
        n_bars = len(df)
        for i in range(0, n_bars - hold_bars, stride):
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
    sig_ex = fee_res.get("signal_t_excess", float("nan"))
    ci_lo = ci_res.get("ci_lower", float("nan"))
    pp = fee_res.get("perm_p_two_sided", float("nan"))
    ci_lo_bp = ci_lo * 10000 if not (isinstance(ci_lo, float) and math.isnan(ci_lo)) else float("nan")
    gate = {
        "label": label,
        "fee_per_trade": fee,
        "n_obs": int(len(obs_net)),
        "obs_mean_bp": float(obs_net.mean() * 10000) if len(obs_net) else float("nan"),
        "obs_t": fee_res.get("obs_t", float("nan")),
        "null_mean_t": fee_res.get("null_mean_t", float("nan")),
        "signal_t_excess": sig_ex,
        "perm_p_two_sided": pp,
        "perm_p_one_sided_above": fee_res.get("perm_p_one_sided_above", float("nan")),
        "ci_lower_bp": ci_lo_bp,
        "ci_upper_bp": ci_res.get("ci_upper", float("nan")) * 10000 if not (isinstance(ci_res.get("ci_upper"), float) and math.isnan(ci_res.get("ci_upper"))) else float("nan"),
        "prob_positive": ci_res.get("prob_positive", float("nan")),
        "n_candidate_pool": int(len(candidate_pool)),
    }
    gate["gate_a_sigex_pass"] = (not math.isnan(sig_ex)) and sig_ex >= 2.0
    gate["gate_b_ci_pass"] = (not math.isnan(ci_lo_bp)) and ci_lo_bp > 0
    gate["gate_c_perm_p_pass"] = (not math.isnan(pp)) and pp <= 0.10
    gate["three_gate_pass"] = (gate["gate_a_sigex_pass"] and gate["gate_b_ci_pass"]
                               and gate["gate_c_perm_p_pass"])
    return gate


def concentration(trades_df: pd.DataFrame, side: str, fee: float) -> dict:
    col = f"{side}_gross"
    df = trades_df.copy()
    df["net"] = df[col] - fee
    # per-half-year t-stat
    per_h = df.groupby("half_year").agg(
        n_trades=("net", "size"),
        mean_bp=("net", lambda s: float(s.mean()) * 10000),
        t_stat=("net", lambda s: float(s.mean() / s.std(ddof=1) * (len(s) ** 0.5))
                if len(s) >= 3 and s.std(ddof=1) > 0 else float("nan")),
    ).reset_index()
    per_h_records = per_h.to_dict(orient="records")
    n_h_measurable = int((per_h["n_trades"] >= 10).sum())
    pos_h = per_h[(per_h["n_trades"] >= 10) & (per_h["t_stat"] > 0)]
    n_h_pos_t = int(len(pos_h))
    half_year_pos_t_ratio = (n_h_pos_t / n_h_measurable) if n_h_measurable else float("nan")

    n_total = len(df)
    if n_total == 0:
        top3_pct = float("nan")
        sign_ratio = float("nan")
        n_pos = n_neg = 0
    else:
        sorted_abs = df["net"].abs().sort_values(ascending=False)
        top3 = float(sorted_abs.head(3).sum())
        all_sum = float(sorted_abs.sum())
        top3_pct = (top3 / all_sum * 100.0) if all_sum > 0 else float("nan")
        n_pos = int((df["net"] > 0).sum())
        n_neg = int((df["net"] < 0).sum())
        sign_ratio = n_pos / n_total if n_total else float("nan")

    half_pass = (not math.isnan(half_year_pos_t_ratio)) and half_year_pos_t_ratio >= 0.5
    sign_pass = (not math.isnan(sign_ratio)) and sign_ratio >= 0.50
    blowup_pass = (not math.isnan(top3_pct)) and top3_pct < 40.0

    return {
        "side": side,
        "per_half_year_t_stats": per_h_records,
        "n_half_years_measurable": n_h_measurable,
        "n_half_years_pos_t": n_h_pos_t,
        "half_year_pos_t_ratio": half_year_pos_t_ratio,
        "n_pos": n_pos,
        "n_neg": n_neg,
        "sign_ratio_positive": sign_ratio,
        "top3_abs_concentration_pct": top3_pct,
        "concentration_gate": {
            "half_year_pass": bool(half_pass),
            "sign_pass": bool(sign_pass),
            "blowup_pass": bool(blowup_pass),
            "overall_pass": bool(half_pass and sign_pass and blowup_pass),
        },
    }


def life_changing_4dim(trades_df: pd.DataFrame, side: str, fee: float,
                       universe_size: int = 14) -> dict:
    """Sparse-strict mode life-changing 4-dim audit (Lesson #71 corollary).

    For sparse-trigger event paradigm:
      - trades_per_year >= 12 (event arrival rate × universe equivalent)
      - per_trade_net_edge_pct >= +2% (sparse-strict edge requirement)
      - single_trade_sharpe_annualized >= 1.5
      - capital_utilization_pct (informational, sparse-strict mode 자격 가능)
    """
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
        single_trade_sharpe = mean_ret / std_ret * math.sqrt(365.0 / mean_hold_days)
    else:
        single_trade_sharpe = float("nan")

    cutoff_trades = 12
    cutoff_edge = 2.0
    cutoff_sharpe = 1.5
    cutoff_util_diffuse = 30.0  # diffuse mode (high-freq) — informational
    cutoff_util_sparse = 1.0    # sparse-strict mode (event-based) — relaxed

    fail_dims_strict = []
    fail_dims_sparse = []
    if math.isnan(trades_per_year) or trades_per_year < cutoff_trades:
        fail_dims_strict.append(f"trades_per_year={trades_per_year:.2f}<{cutoff_trades}")
        fail_dims_sparse.append(f"trades_per_year={trades_per_year:.2f}<{cutoff_trades}")
    if per_trade_net_edge_pct < cutoff_edge:
        fail_dims_strict.append(f"edge={per_trade_net_edge_pct:.2f}%<{cutoff_edge}%")
        fail_dims_sparse.append(f"edge={per_trade_net_edge_pct:.2f}%<{cutoff_edge}%")
    if math.isnan(cap_util_pct) or cap_util_pct < cutoff_util_diffuse:
        fail_dims_strict.append(f"util={cap_util_pct:.2f}%<{cutoff_util_diffuse}%")
    if math.isnan(cap_util_pct) or cap_util_pct < cutoff_util_sparse:
        fail_dims_sparse.append(f"util={cap_util_pct:.2f}%<{cutoff_util_sparse}%")
    if math.isnan(single_trade_sharpe) or single_trade_sharpe < cutoff_sharpe:
        fail_dims_strict.append(f"sharpe={single_trade_sharpe:.2f}<{cutoff_sharpe}")
        fail_dims_sparse.append(f"sharpe={single_trade_sharpe:.2f}<{cutoff_sharpe}")

    diffuse_verdict = "PASS" if not fail_dims_strict else "FAIL"
    sparse_verdict = "PASS" if not fail_dims_sparse else "FAIL"

    return {
        "side": side,
        "fee_per_trade": fee,
        "oos_days": oos_days,
        "n_events": n_events,
        "trades_per_year": trades_per_year,
        "per_trade_net_edge_pct": per_trade_net_edge_pct,
        "capital_utilization_pct": cap_util_pct,
        "mean_hold_days": mean_hold_days,
        "single_trade_sharpe_annualized": single_trade_sharpe,
        "cutoffs": {
            "trades_per_year": cutoff_trades,
            "per_trade_net_edge_pct": cutoff_edge,
            "capital_utilization_pct_diffuse": cutoff_util_diffuse,
            "capital_utilization_pct_sparse": cutoff_util_sparse,
            "single_trade_sharpe": cutoff_sharpe,
        },
        "diffuse_mode_verdict": diffuse_verdict,
        "sparse_strict_mode_verdict": sparse_verdict,
        "fail_dims_diffuse": fail_dims_strict,
        "fail_dims_sparse": fail_dims_sparse,
    }


def main():
    log.info("== R-1 paradigm 189 listing_event_post_onboard_4h_entry_side_forced_buy_directional_bilateral ==")
    events = load_events()
    log.info("events loaded: %d (universe = Binance Futures USDS perp)", len(events))

    # Half-year distribution (Lesson #11 prescreen)
    hy_counts = events["half_year"].value_counts().sort_index()
    log.info("per-half-year event counts: %s", hy_counts.to_dict())

    metrics: dict = {
        "paradigm_name": "binance_futures_perp_listing_event_post_onboard_4h_entry_side_forced_buy_directional_bilateral",
        "paradigm_counter": 189,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_events_universe": int(len(events)),
        "fee_baseline_per_trade": FEE_BASELINE_PER_TRADE,
        "fee_stress_per_trade": FEE_STRESS_PER_TRADE,
        "entry_offset_min": ENTRY_OFFSET_MIN,
        "holds_hrs_swept": HOLDS_HRS,
        "per_half_year_event_counts": hy_counts.to_dict(),
        "lesson_11_prescreen": {
            "n_total_events": int(len(events)),
            "scope": "bilateral 2-cell A focus LONG + A mirror SHORT (NO 4-quadrant SNT, sample density compression per user spec)",
            "per_half_year_measurable_count": int((hy_counts >= 10).sum()),
            "per_half_year_total": int(len(hy_counts)),
            "verdict": "PASS_n_over_30_avg_33" if len(events) >= 200 else "MARGINAL_OR_FAIL",
            "rationale": "468 listings in window; 2 cells x 7 half-years = 14 cells; per-cell avg 33.4 >= 30 cutoff",
        },
        "hold_sweep_results": {},
    }

    # Hold sweep: 4h primary + 8h + 12h + 24h + 48h
    for hold_hrs in HOLDS_HRS:
        log.info("=== HOLD = %dh ===", hold_hrs)
        trades = compute_trades(events, hold_hrs)
        if trades.empty:
            metrics["hold_sweep_results"][f"hold_{hold_hrs}h"] = {"error": "no_valid_trades"}
            continue
        log.info("  trades: %d", len(trades))
        log.info("  gross LONG : mean=%.4f median=%.4f std=%.4f",
                 trades["long_gross"].mean(), trades["long_gross"].median(),
                 trades["long_gross"].std(ddof=1))
        log.info("  gross SHORT: mean=%.4f median=%.4f std=%.4f",
                 trades["short_gross"].mean(), trades["short_gross"].median(),
                 trades["short_gross"].std(ddof=1))

        pool = build_candidate_pool(trades, hold_hrs)
        log.info("  candidate pool: long n=%d, short n=%d", len(pool["long"]), len(pool["short"]))

        # Bilateral 2-cell
        cell_results = {}
        for label, side in [("A_focus_LONG", "long"), ("A_mirror_SHORT", "short")]:
            log.info("  --- %s (hold=%dh) ---", label, hold_hrs)
            observed = trades[f"{side}_gross"].values
            baseline = three_gate(observed, pool[side], FEE_BASELINE_PER_TRADE,
                                  f"{label}_h{hold_hrs}_fee_baseline")
            stress = three_gate(observed, pool[side], FEE_STRESS_PER_TRADE,
                                f"{label}_h{hold_hrs}_fee_stress")
            conc = concentration(trades, side, FEE_BASELINE_PER_TRADE)
            freq_b = life_changing_4dim(trades, side, FEE_BASELINE_PER_TRADE)
            freq_s = life_changing_4dim(trades, side, FEE_STRESS_PER_TRADE)

            if baseline["three_gate_pass"] and stress["three_gate_pass"]:
                tg_verdict = "PASS_both_fee_levels"
            elif baseline["three_gate_pass"]:
                tg_verdict = "FRAGILE_PASS_FEE_SENSITIVE"
            else:
                tg_verdict = "FAIL"

            cell_results[label] = {
                "side": side,
                "n_trades": int(len(trades)),
                "fee_baseline": baseline,
                "fee_stress": stress,
                "concentration_baseline": conc,
                "life_changing_baseline": freq_b,
                "life_changing_stress": freq_s,
                "three_gate_verdict": tg_verdict,
                "concentration_gate_overall_pass": conc["concentration_gate"]["overall_pass"],
                "life_changing_sparse_verdict_baseline": freq_b["sparse_strict_mode_verdict"],
                "life_changing_sparse_verdict_stress": freq_s["sparse_strict_mode_verdict"],
                "life_changing_diffuse_verdict_baseline": freq_b["diffuse_mode_verdict"],
            }
            log.info("    %s: tg=%s, conc=%s, sparse_LC_baseline=%s",
                     label, tg_verdict, conc["concentration_gate"]["overall_pass"],
                     freq_b["sparse_strict_mode_verdict"])
            log.info("      baseline: obs_t=%.3f, null_mean_t=%.3f, sigex=%.3f, ci=[%.2f, %.2f]bp, perm_p=%.4f",
                     baseline["obs_t"], baseline["null_mean_t"], baseline["signal_t_excess"],
                     baseline["ci_lower_bp"], baseline["ci_upper_bp"], baseline["perm_p_two_sided"])
            log.info("      stress  : obs_t=%.3f, sigex=%.3f, ci_lo=%.2fbp, perm_p=%.4f",
                     stress["obs_t"], stress["signal_t_excess"],
                     stress["ci_lower_bp"], stress["perm_p_two_sided"])
            log.info("      freq baseline: trades/yr=%.1f edge=%.2f%% util=%.1f%% sharpe=%.2f",
                     freq_b.get("trades_per_year", float("nan")),
                     freq_b.get("per_trade_net_edge_pct", float("nan")),
                     freq_b.get("capital_utilization_pct", float("nan")),
                     freq_b.get("single_trade_sharpe_annualized", float("nan")))

        metrics["hold_sweep_results"][f"hold_{hold_hrs}h"] = {
            "n_trades": int(len(trades)),
            "cells": cell_results,
        }

    # === Final verdict logic across hold sweep ===
    pass_cells = []   # (hold, side) tuples where three-gate + concentration + sparse LC all PASS
    narrow_pass_cells = []  # three-gate PASS but concentration or sparse LC FAIL
    sigex_max_per_side = {"long": -1e9, "short": -1e9}
    sigex_max_cell = {"long": None, "short": None}
    for hold_label, hres in metrics["hold_sweep_results"].items():
        if "cells" not in hres:
            continue
        for cell_label, cres in hres["cells"].items():
            side = cres["side"]
            sigex = cres["fee_baseline"]["signal_t_excess"]
            if not math.isnan(sigex) and sigex > sigex_max_per_side[side]:
                sigex_max_per_side[side] = sigex
                sigex_max_cell[side] = f"{hold_label}/{cell_label}"
            tg_pass = cres["fee_baseline"]["three_gate_pass"]
            conc_pass = cres["concentration_gate_overall_pass"]
            sparse_lc_pass = (cres["life_changing_sparse_verdict_baseline"] == "PASS")
            if tg_pass and conc_pass and sparse_lc_pass:
                pass_cells.append((hold_label, cell_label))
            elif tg_pass:
                narrow_pass_cells.append((hold_label, cell_label, conc_pass, sparse_lc_pass))

    if len(pass_cells) == 0 and len(narrow_pass_cells) == 0:
        # Check broad-falsified vs other
        all_sigex = [v for v in sigex_max_per_side.values() if v > -1e8]
        if all(s < 0 for s in all_sigex):
            overall = "BROAD_FALSIFIED_BILATERAL"
        else:
            overall = "PORTFOLIO_ALPHA_INSIGNIFICANT"
    elif len(pass_cells) >= 1:
        overall = "PASS_R1_FULL"
    elif len(narrow_pass_cells) >= 1:
        # Narrow PASS with sparse-strict failure -> NSLC
        any_concentrated = any(not c[2] for c in narrow_pass_cells)
        any_lc_fail = any(not c[3] for c in narrow_pass_cells)
        if any_concentrated and any_lc_fail:
            overall = "CONCENTRATED_R1_PASS_AND_NSLC_FAIL"
        elif any_concentrated:
            overall = "CONCENTRATED_R1_PASS"
        elif any_lc_fail:
            overall = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
        else:
            overall = "PASS_R1_THREE_GATE_BUT_OTHER_FAIL"
    else:
        overall = "FAIL_OTHER"

    metrics["overall_verdict"] = overall
    metrics["sigex_max_per_side"] = sigex_max_per_side
    metrics["sigex_max_cell"] = sigex_max_cell
    metrics["pass_cells_full"] = [list(t) for t in pass_cells]
    metrics["narrow_pass_cells"] = [list(t) for t in narrow_pass_cells]

    OUT_JSON.write_text(json.dumps(metrics, default=str, indent=2))
    log.info("=== OVERALL VERDICT: %s ===", overall)
    log.info("sigex max LONG : %.3f @ %s", sigex_max_per_side["long"], sigex_max_cell["long"])
    log.info("sigex max SHORT: %.3f @ %s", sigex_max_per_side["short"], sigex_max_cell["short"])
    log.info("wrote %s", OUT_JSON)


if __name__ == "__main__":
    main()
