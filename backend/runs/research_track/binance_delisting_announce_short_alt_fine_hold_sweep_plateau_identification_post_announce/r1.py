"""R-1 PoC for paradigm 190 `binance_delisting_announce_short_alt_fine_hold_sweep_plateau_identification_post_announce`.

Hypothesis
----------
paradigm 87 R-1 PASS_R1_FULL (sigex +2.23 / 4-dim ALL PASS / trades/yr 40.5 / edge 14.6% / sharpe 6.49)
→ R-2 FRAGILE_TEMPORAL_WF_FAIL (TS-CV 1/5 PASS, single 2025Q4 outlier dominance, Lesson #26 small-sample
Concentration Gate per-quarter blind spot).

Fine-hold-sweep (1h / 2h / 4h / 8h / 12h / 24h / 48h post-announce) for plateau identification
to find alpha-bearing window with monotone sigex + sustained edge + stable concentration.

Paradigm 87 only measured 1d hold (announce+5m → delist-24h ≈ avg 3.3d hold). This paradigm
sweeps 7 specific holds post-announce to localize precise window.

Direction: Bilateral A focus SHORT + A mirror LONG (paradigm 87 mirror symmetric per Lesson #19).
B same-sign / B mirror deferred (Lesson #11 sample density preservation).

Cells = 7 holds × 2 directions = 14 cells.

R-0 prescreen verdicts (all PASS, see agent prescreen block):
- P1 Lesson #70 corollary: PROCEED (b) R-1 PASS follow-up hold refinement (NOT spec-adaptive expansion)
- P3 Lesson #11 sample density: n=57 per hold cell PASS (within-paradigm parameter sweep)
- P5 Lesson #67/#68 ESCAPE: confirmed (idiosyncratic event marker, post-announce window not session-boundary)
- P6 Lesson #71 corollary: sparse-strict mode 자격 후보

R-1 stat suite per cell
-----------------------
- 3-gate (per direction per hold):
    * signal_t_excess >= 2.0 (fee-aware perm)
    * ci_lower > 0
    * perm_p_two_sided <= 0.10
- Concentration Gate adapted (per-quarter t / sign / blowup)
- 4-dim Frequency-First Gate per hold (trades/yr, edge%, util%, sharpe)
- Fee Stress (baseline 8bp / stress 25bp)

Plateau identification
----------------------
Best 3 consecutive holds with:
- sigex monotone (no major drop)
- net edge sustained
- concentration_gate.overall_pass = True
- all 3 gates PASS

paradigm 87 baseline comparison
-------------------------------
1d hold spec (announce+5m → delist-24h) results from r1__metrics.json.
"""
from __future__ import annotations
import csv
import json
import logging
import math
import sys
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
log = logging.getLogger("p190_r1")

DIR = Path(__file__).resolve().parent
CACHE = DIR / "ohlcv_cache_local"
EVENTS_CSV = DIR.parent / "binance_delisting_announce_short_alt" / "delisting_events.csv"
OUT_JSON = DIR / "r1__metrics.json"

FEE_BASELINE_PER_TRADE = 0.0008
FEE_STRESS_PER_TRADE = 0.0025
ENTRY_OFFSET_MIN = 5

# 7 hold horizons (minutes post-announce-entry)
HOLD_HORIZONS_MIN = [60, 120, 240, 480, 720, 1440, 2880]  # 1h, 2h, 4h, 8h, 12h, 24h, 48h
HOLD_LABELS = ["1h", "2h", "4h", "8h", "12h", "24h", "48h"]


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


def load_sym_ohlcv(sym: str):
    p = CACHE / f"{sym}.joblib"
    if not p.exists():
        return None
    df = joblib.load(p)
    if df is None or df.empty:
        return None
    return df.sort_index()


def get_close_at_or_after(df: pd.DataFrame, ts: pd.Timestamp):
    idx = df.index.searchsorted(ts, side="left")
    if idx >= len(df):
        return None
    return df.index[idx], float(df["close"].iloc[idx])


def compute_trades_for_hold(events: pd.DataFrame, hold_min: int) -> pd.DataFrame:
    """For each event: entry = announce + 5min, exit = entry + hold_min."""
    rows = []
    skipped = 0
    for _, row in events.iterrows():
        sym = row["symbol"]
        ann = row["announce_ts"]
        de = row["delist_ts"]
        entry_target = ann + pd.Timedelta(minutes=ENTRY_OFFSET_MIN)
        exit_target = entry_target + pd.Timedelta(minutes=hold_min)
        # Skip if exit_target > delist_ts (post-delist data unavailable for paradigm scope)
        if exit_target > de:
            # use cap at delist_ts - 1min (pre-delist last available bar)
            exit_target = de - pd.Timedelta(minutes=1)
            if exit_target <= entry_target:
                skipped += 1
                continue
        df = load_sym_ohlcv(sym)
        if df is None:
            skipped += 1
            continue
        e = get_close_at_or_after(df, entry_target)
        x = get_close_at_or_after(df, exit_target)
        if e is None or x is None:
            skipped += 1
            continue
        entry_ts, entry_px = e
        exit_ts, exit_px = x
        if exit_ts <= entry_ts or entry_px <= 0 or exit_px <= 0:
            skipped += 1
            continue
        long_gross = (exit_px / entry_px) - 1.0
        short_gross = -long_gross
        hold_days = (exit_ts - entry_ts).total_seconds() / 86400.0
        rows.append({
            "symbol": sym,
            "announce_ts": ann,
            "delist_ts": de,
            "entry_ts": entry_ts,
            "exit_ts": exit_ts,
            "hold_days": hold_days,
            "entry_px": entry_px,
            "exit_px": exit_px,
            "long_gross": long_gross,
            "short_gross": short_gross,
            "quarter": str(pd.Timestamp(ann).to_period("Q")),
        })
    return pd.DataFrame(rows), skipped


def build_candidate_pool_for_hold(trades_df: pd.DataFrame, hold_min: int) -> dict:
    """Per-event candidate pool: random non-trigger same-length windows in the pre/post window."""
    long_pool = []
    short_pool = []
    hold_bars = max(1, hold_min)  # 1m bars
    stride = max(1, hold_bars // 3)
    for _, row in trades_df.iterrows():
        sym = row["symbol"]
        df = load_sym_ohlcv(sym)
        if df is None or len(df) < hold_bars + 5:
            continue
        for i in range(0, len(df) - hold_bars, stride):
            ep = float(df["close"].iloc[i])
            xp = float(df["close"].iloc[i + hold_bars])
            if ep <= 0 or xp <= 0:
                continue
            r = xp / ep - 1.0
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
        "ci_lower_bp": (ci_res.get("ci_lower", float("nan")) * 10000
                        if not math.isnan(ci_res.get("ci_lower", float("nan"))) else float("nan")),
        "ci_upper_bp": (ci_res.get("ci_upper", float("nan")) * 10000
                        if not math.isnan(ci_res.get("ci_upper", float("nan"))) else float("nan")),
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


def concentration_block(trades_df: pd.DataFrame, side: str, fee: float) -> dict:
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
    n_q_meas = int((per_q["n_trades"] >= 10).sum())
    pos_q = per_q[(per_q["n_trades"] >= 10) & (per_q["t_stat"] > 0)]
    n_q_pos_t = int(len(pos_q))
    quarter_pos_t_ratio = (n_q_pos_t / n_q_meas) if n_q_meas else float("nan")

    abs_net = df["net"].abs().sort_values(ascending=False)
    total_abs = abs_net.sum()
    top3 = abs_net.head(3).sum()
    top3_concentration_pct = (top3 / total_abs * 100) if total_abs > 0 else float("nan")

    n_pos = int((df["net"] > 0).sum())
    n_neg = int((df["net"] < 0).sum())
    sign_ratio_positive = n_pos / len(df) if len(df) else float("nan")

    quarter_pass = (not math.isnan(quarter_pos_t_ratio)) and quarter_pos_t_ratio >= 0.5
    sign_pass = (not math.isnan(sign_ratio_positive)) and sign_ratio_positive >= 0.5
    blowup_pass = (not math.isnan(top3_concentration_pct)) and top3_concentration_pct <= 50.0

    return {
        "side": side,
        "per_quarter_t_stats": per_q_records,
        "n_quarters_measurable": n_q_meas,
        "n_quarters_pos_t": n_q_pos_t,
        "quarter_pos_t_ratio": quarter_pos_t_ratio,
        "n_pos": n_pos,
        "n_neg": n_neg,
        "sign_ratio_positive": sign_ratio_positive,
        "top3_abs_concentration_pct": top3_concentration_pct,
        "concentration_gate": {
            "quarter_pass": quarter_pass,
            "sign_pass": sign_pass,
            "blowup_pass": blowup_pass,
            "overall_pass": quarter_pass and sign_pass and blowup_pass,
        },
    }


def frequency_first_gate(trades_df: pd.DataFrame, side: str, fee: float,
                         oos_days: float) -> dict:
    col = f"{side}_gross"
    df = trades_df.copy()
    df["net"] = df[col] - fee
    n_events = len(df)
    trades_per_year = n_events / (oos_days / 365.25) if oos_days > 0 else float("nan")
    per_trade_net_edge_pct = float(df["net"].mean()) * 100 if n_events else float("nan")
    mean_hold_days = float(df["hold_days"].mean()) if n_events else float("nan")
    capital_utilization_pct = (mean_hold_days * n_events / oos_days * 100) if oos_days > 0 else float("nan")
    if n_events > 1 and df["net"].std(ddof=1) > 0:
        sharpe_per_trade = df["net"].mean() / df["net"].std(ddof=1)
        if mean_hold_days > 0:
            sharpe_annualized = sharpe_per_trade * math.sqrt(365.25 / mean_hold_days)
        else:
            sharpe_annualized = float("nan")
    else:
        sharpe_annualized = float("nan")

    cutoffs = {
        "trades_per_year": 12,
        "per_trade_net_edge_pct": 2.0,
        "capital_utilization_pct": 30.0,
        "single_trade_sharpe": 1.5,
    }
    fail_dims = []
    if not math.isnan(trades_per_year) and trades_per_year < cutoffs["trades_per_year"]:
        fail_dims.append(f"trades_per_year={trades_per_year:.1f}<{cutoffs['trades_per_year']}")
    if not math.isnan(per_trade_net_edge_pct) and per_trade_net_edge_pct < cutoffs["per_trade_net_edge_pct"]:
        fail_dims.append(f"per_trade_net_edge_pct={per_trade_net_edge_pct:.2f}<{cutoffs['per_trade_net_edge_pct']}")
    if not math.isnan(capital_utilization_pct) and capital_utilization_pct < cutoffs["capital_utilization_pct"]:
        fail_dims.append(f"capital_utilization_pct={capital_utilization_pct:.2f}<{cutoffs['capital_utilization_pct']}")
    if not math.isnan(sharpe_annualized) and sharpe_annualized < cutoffs["single_trade_sharpe"]:
        fail_dims.append(f"single_trade_sharpe={sharpe_annualized:.2f}<{cutoffs['single_trade_sharpe']}")

    return {
        "side": side,
        "fee_per_trade": fee,
        "oos_days": oos_days,
        "n_events": n_events,
        "trades_per_year": trades_per_year,
        "per_trade_net_edge_pct": per_trade_net_edge_pct,
        "capital_utilization_pct": capital_utilization_pct,
        "mean_hold_days": mean_hold_days,
        "single_trade_sharpe_annualized": sharpe_annualized,
        "cutoffs": cutoffs,
        "gate_verdict": "PASS" if not fail_dims else "FAIL",
        "fail_dims": fail_dims,
    }


def evaluate_cell(events: pd.DataFrame, hold_min: int, hold_label: str,
                  side: str, oos_days: float) -> dict:
    """One (hold × direction) cell evaluation."""
    trades_df, skipped = compute_trades_for_hold(events, hold_min)
    if len(trades_df) < 10:
        return {
            "hold_label": hold_label,
            "hold_min": hold_min,
            "side": side,
            "n_obs": len(trades_df),
            "n_skipped": skipped,
            "verdict": "SAMPLE_INSUFFICIENT",
        }
    pool = build_candidate_pool_for_hold(trades_df, hold_min)
    obs_gross = trades_df[f"{side}_gross"].to_numpy()
    pool_side = pool[side]

    fee_base = three_gate(obs_gross, pool_side, FEE_BASELINE_PER_TRADE,
                          label=f"{hold_label}_{side}_fee_baseline")
    fee_stress = three_gate(obs_gross, pool_side, FEE_STRESS_PER_TRADE,
                            label=f"{hold_label}_{side}_fee_stress")
    conc = concentration_block(trades_df, side, FEE_BASELINE_PER_TRADE)
    freq_base = frequency_first_gate(trades_df, side, FEE_BASELINE_PER_TRADE, oos_days)
    freq_stress = frequency_first_gate(trades_df, side, FEE_STRESS_PER_TRADE, oos_days)

    return {
        "hold_label": hold_label,
        "hold_min": hold_min,
        "side": side,
        "n_obs": len(trades_df),
        "n_skipped": skipped,
        "fee_baseline": fee_base,
        "fee_stress": fee_stress,
        "concentration_baseline": conc,
        "frequency_first_gate_baseline": freq_base,
        "frequency_first_gate_stress": freq_stress,
        "three_gate_verdict": "PASS_both_fee_levels" if (fee_base["three_gate_pass"] and fee_stress["three_gate_pass"]) else (
            "PASS_baseline_only" if fee_base["three_gate_pass"] else "FAIL"),
        "concentration_gate_overall_pass": conc["concentration_gate"]["overall_pass"],
        "frequency_gate_baseline_verdict": freq_base["gate_verdict"],
        "frequency_gate_stress_verdict": freq_stress["gate_verdict"],
    }


def find_plateau(cells_by_hold: list) -> dict:
    """Find best 3-consecutive-hold plateau.

    Plateau requires:
      - All 3 holds: three_gate baseline PASS AND fee_stress PASS
      - All 3 holds: concentration_gate overall_pass = True
      - sigex monotone-ish (no drop >50% from peak)
      - net edge sustained
    """
    n = len(cells_by_hold)
    plateau_candidates = []
    for i in range(n - 2):
        triple = cells_by_hold[i:i + 3]
        all_pass = all(c.get("three_gate_verdict") == "PASS_both_fee_levels" for c in triple)
        all_conc_pass = all(c.get("concentration_gate_overall_pass", False) for c in triple)
        sigex_vals = [c["fee_baseline"]["signal_t_excess"] for c in triple if "fee_baseline" in c]
        if len(sigex_vals) != 3:
            continue
        edge_vals = [c["frequency_first_gate_baseline"]["per_trade_net_edge_pct"] for c in triple]
        # Sustained edge: all >= +2%
        edge_sustained = all(e >= 2.0 for e in edge_vals)
        # Monotone-ish: peak sigex / min sigex >= 0.5 (within-plateau coefficient of variation moderate)
        peak = max(sigex_vals)
        floor = min(sigex_vals)
        plateau_stable = (peak > 0) and (floor / peak >= 0.5) if peak > 0 else False

        plateau_candidates.append({
            "hold_labels": [c["hold_label"] for c in triple],
            "hold_mins": [c["hold_min"] for c in triple],
            "all_three_gate_pass": all_pass,
            "all_concentration_pass": all_conc_pass,
            "sigex_vals": sigex_vals,
            "edge_vals_pct": edge_vals,
            "edge_sustained": edge_sustained,
            "plateau_stable": plateau_stable,
            "mean_sigex": float(np.mean(sigex_vals)),
            "mean_edge_pct": float(np.mean(edge_vals)),
            "plateau_overall_pass": all_pass and all_conc_pass and edge_sustained and plateau_stable,
        })
    # Pick best plateau by mean_sigex among those overall_pass; else best by mean_sigex
    passing = [p for p in plateau_candidates if p["plateau_overall_pass"]]
    if passing:
        best = max(passing, key=lambda p: p["mean_sigex"])
        verdict = "PLATEAU_FOUND"
    elif plateau_candidates:
        best = max(plateau_candidates, key=lambda p: p["mean_sigex"])
        verdict = "NO_QUALIFYING_PLATEAU"
    else:
        best = None
        verdict = "INSUFFICIENT_CELLS"
    return {
        "all_candidates": plateau_candidates,
        "best_plateau": best,
        "verdict": verdict,
    }


def main():
    events = load_events()
    log.info("loaded %d events", len(events))

    # OOS days = earliest announce_ts -> latest (announce_ts + 48h)
    earliest_ann = events["announce_ts"].min()
    latest_exit = (events["announce_ts"] + pd.Timedelta(hours=48)).max()
    oos_days = (latest_exit - earliest_ann).total_seconds() / 86400.0
    log.info("OOS window: %s -> %s = %.2f days", earliest_ann, latest_exit, oos_days)

    # 14 cells = 7 holds × 2 directions
    all_cells = {}
    cells_by_hold_short = []
    cells_by_hold_long = []
    for hold_min, hold_label in zip(HOLD_HORIZONS_MIN, HOLD_LABELS):
        for side in ("short", "long"):
            key = f"{hold_label}_{side}"
            log.info("evaluating cell %s ...", key)
            cell = evaluate_cell(events, hold_min, hold_label, side, oos_days)
            all_cells[key] = cell
            if side == "short":
                cells_by_hold_short.append(cell)
            else:
                cells_by_hold_long.append(cell)
            v = cell.get("three_gate_verdict", "?")
            n_obs = cell.get("n_obs", 0)
            if "fee_baseline" in cell:
                sigex = cell["fee_baseline"].get("signal_t_excess", float("nan"))
                edge = cell["frequency_first_gate_baseline"]["per_trade_net_edge_pct"]
                log.info("  %s: n=%d verdict=%s sigex=%.2f edge=%.2f%%", key, n_obs, v, sigex, edge)

    # Plateau identification on SHORT direction (A focus primary)
    plateau_short = find_plateau(cells_by_hold_short)
    plateau_long = find_plateau(cells_by_hold_long)

    # paradigm 87 baseline reference
    p87_baseline = {
        "spec": "announce+5min -> delist-24h (~3.3d avg hold)",
        "side": "short",
        "n_obs": 57,
        "fee_baseline": {
            "signal_t_excess": 2.233462446711633,
            "perm_p_two_sided": 0.062,
            "ci_lower_bp": 781.9055597691789,
            "obs_mean_bp": 1380.8157486482387,
            "obs_win_rate": 0.7192982456140351,
            "three_gate_pass": True,
        },
        "concentration": {
            "quarter_pos_t_ratio": 1.0,
            "n_quarters_measurable": 3,
            "sign_ratio_positive": 0.7192982456140351,
            "overall_pass": True,
        },
        "frequency_first_gate_baseline": {
            "trades_per_year": 40.4901110129015,
            "per_trade_net_edge_pct": 14.631786636076852,
            "capital_utilization_pct": 36.654665271909984,
            "single_trade_sharpe_annualized": 6.486942037287733,
            "gate_verdict": "PASS",
        },
        "r2_outcome": "FRAGILE_TEMPORAL_WF_FAIL (TS-CV 1/5 PASS, Q4-2025 single-quarter outlier)",
    }

    # Overall paradigm 190 verdict
    # PASS_R1_FULL: SHORT plateau verdict = PLATEAU_FOUND
    # NSLC_FAIL: SHORT three-gate cells PASS but 4-dim freq FAIL
    # BROAD_FALSIFIED: SHORT zero cells with three_gate_pass
    n_short_pass = sum(1 for c in cells_by_hold_short if c.get("three_gate_verdict") == "PASS_both_fee_levels")
    n_long_pass = sum(1 for c in cells_by_hold_long if c.get("three_gate_verdict") == "PASS_both_fee_levels")
    n_short_freq_pass = sum(1 for c in cells_by_hold_short
                            if c.get("frequency_gate_baseline_verdict") == "PASS"
                            and c.get("frequency_gate_stress_verdict") == "PASS")

    if plateau_short["verdict"] == "PLATEAU_FOUND" and n_short_freq_pass >= 1:
        overall = "PASS_R1_FULL_PLATEAU"
    elif n_short_pass == 0:
        overall = "BROAD_FALSIFIED"
    elif plateau_short["verdict"] == "NO_QUALIFYING_PLATEAU" and n_short_pass >= 1:
        # Some cells pass but no plateau (isolated PASS cells)
        # Check Lesson #20 sign-cond + Lesson #16 Concentration
        passing_cells_with_conc = [
            c for c in cells_by_hold_short
            if c.get("three_gate_verdict") == "PASS_both_fee_levels"
            and c.get("concentration_gate_overall_pass")
        ]
        if passing_cells_with_conc:
            # Has at least one isolated PASS cell with concentration — check life-changing 4-dim
            life_changing_passing = [
                c for c in passing_cells_with_conc
                if c.get("frequency_gate_baseline_verdict") == "PASS"
                and c.get("frequency_gate_stress_verdict") == "PASS"
            ]
            if life_changing_passing:
                overall = "NARROW_ISOLATED_PASS_LIFE_CHANGING_OK"  # custom: isolated PASS holds with 4-dim
            else:
                overall = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
        else:
            overall = "ISOLATED_PASS_CONCENTRATION_FAIL"
    else:
        overall = "FRAGILE_OR_INCONCLUSIVE"

    out = {
        "paradigm_name": "binance_delisting_announce_short_alt_fine_hold_sweep_plateau_identification_post_announce",
        "paradigm_counter": 190,
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "n_events": len(events),
        "fee_baseline_per_trade": FEE_BASELINE_PER_TRADE,
        "fee_stress_per_trade": FEE_STRESS_PER_TRADE,
        "entry_offset_min": ENTRY_OFFSET_MIN,
        "hold_horizons_min": HOLD_HORIZONS_MIN,
        "hold_labels": HOLD_LABELS,
        "oos_days": oos_days,
        "lesson_70_corollary_scope_verdict": "PROCEED_R1_PASS_FOLLOWUP_HOLD_REFINEMENT_NOT_SPEC_ADAPTIVE",
        "lesson_11_sample_density_verdict": "PASS_n57_per_hold_within_paradigm_parameter_sweep",
        "paradigm_87_baseline_reference": p87_baseline,
        "cells": all_cells,
        "n_short_cells_three_gate_pass": n_short_pass,
        "n_long_cells_three_gate_pass": n_long_pass,
        "n_short_cells_freq_gate_pass": n_short_freq_pass,
        "plateau_short": plateau_short,
        "plateau_long": plateau_long,
        "overall_verdict": overall,
    }

    # JSON-serialize NaN-safe
    def clean(o):
        if isinstance(o, dict):
            return {k: clean(v) for k, v in o.items()}
        if isinstance(o, list):
            return [clean(x) for x in o]
        if isinstance(o, float):
            if math.isnan(o):
                return None
            if math.isinf(o):
                return None
            return o
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            v = float(o)
            return None if math.isnan(v) or math.isinf(v) else v
        if isinstance(o, np.ndarray):
            return [clean(x) for x in o.tolist()]
        if isinstance(o, pd.Timestamp):
            return o.isoformat()
        return o

    with open(OUT_JSON, "w") as f:
        json.dump(clean(out), f, indent=2, default=str)
    log.info("WROTE %s", OUT_JSON)
    log.info("OVERALL VERDICT: %s", overall)
    log.info("plateau_short.verdict: %s", plateau_short["verdict"])
    if plateau_short.get("best_plateau"):
        bp = plateau_short["best_plateau"]
        log.info("best_plateau_short: holds=%s sigex=%s edge=%s%%",
                 bp["hold_labels"], bp["sigex_vals"], bp["edge_vals_pct"])


if __name__ == "__main__":
    main()
