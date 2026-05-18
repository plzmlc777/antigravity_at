"""R-1 PoC for paradigm `binance_delisting_announce_short_alt`.

Hypothesis
----------
Binance Futures USDS-M perp delisting announcement triggers forced-exit liquidity
drift; SHORT alpha persists from announce_ts+5min to delist_ts-24h close.

DNA
---
External event injection × forced-exit liquidity × short-side directional.

R-1 stat suite (per paradigm-architect spec)
--------------------------------------------
- Symmetric Negative Test 2-quadrant REDUCED (user-authorized, Lesson #11 + #19):
    * A focus  : SHORT, announce+5min entry -> delist-24h close exit
    * A mirror : LONG,  same window         (oversold-panic-reversal counter-hypothesis)
  (B post-delist 24h continuation deferred to separate R-1 if A focus PASSes.)

- Three-gate (per direction):
    * signal_t_excess >= 2.0        (fee-aware perm vs candidate-window null)
    * ci_lower > 0                  (block bootstrap on observed)
    * perm_p_two_sided <= 0.10

- Concentration Gate (Lesson #16, adapted for one-shot-event paradigm):
    * per-quarter t-stat distribution + ratio of measurable quarters (n>=10) with t>0
    * per-symbol "skip" (each symbol appears once; per-symbol CI = NaN by construction)
    * fallback: per-event sign distribution + magnitude concentration metric (top-3 events
      contribution as % of aggregate mean) — guards against single-blowup cherry-pick.

- 4-dim Frequency-First Gate (life-changing campaign binding):
    * trades_per_year     >= 12
    * per_trade_net_edge  >= +2 %
    * capital_util_pct    >= 30 %  (mean_hold_days × n_events / OOS_days)
    * single_trade_sharpe >= 1.5   (annualized)

- Fee Stress Test (user-mandated):
    * fee_baseline = 8 bp / trade  (16 bp round-trip)
    * fee_stress   = 25 bp / trade (50 bp round-trip)
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

# repo-local utils
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from scripts.research._perm_utils import (  # noqa: E402
    bootstrap_ci,
    fee_aware_perm_test,
)

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
log = logging.getLogger("r1_delisting")

DIR = Path(__file__).resolve().parent
CACHE = DIR / "ohlcv_cache"
EVENTS_CSV = DIR / "delisting_events.csv"
OUT_JSON = DIR / "r1__metrics.json"

FEE_BASELINE_PER_TRADE = 0.0008   # 8 bp one-way × 2 = 16 bp round-trip
FEE_STRESS_PER_TRADE = 0.0025     # 25 bp one-way × 2 = 50 bp round-trip
ENTRY_OFFSET_MIN = 5              # announce_ts + 5 min entry
EXIT_BEFORE_DELIST_MIN = 24 * 60  # delist_ts - 24 h exit

# OOS window for trades/yr denominator: earliest announce_ts -> latest exit_ts
# (computed dynamically from observed events)


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
    # Normalize tz
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
    # index already utc tz-aware
    df = df.sort_index()
    return df


def get_close_at_or_after(df: pd.DataFrame, ts: pd.Timestamp) -> tuple[pd.Timestamp, float] | None:
    """Return (actual_ts, close) at first 1m bar with index >= ts."""
    idx = df.index.searchsorted(ts, side="left")
    if idx >= len(df):
        return None
    actual = df.index[idx]
    return actual, float(df["close"].iloc[idx])


def get_close_at_or_before(df: pd.DataFrame, ts: pd.Timestamp) -> tuple[pd.Timestamp, float] | None:
    """Return (actual_ts, close) at last 1m bar with index <= ts."""
    idx = df.index.searchsorted(ts, side="right") - 1
    if idx < 0:
        return None
    actual = df.index[idx]
    return actual, float(df["close"].iloc[idx])


def compute_trades(events: pd.DataFrame) -> pd.DataFrame:
    """For each (symbol, announce_ts, delist_ts):
        entry  = first 1m bar close >= announce_ts + 5 min
        exit   = last  1m bar close <= delist_ts   - 24 h
        gross_return_long = (exit/entry) - 1
        gross_return_short = -(gross_return_long)   (sign-flip for SHORT)
    """
    out_rows = []
    skipped = 0
    for _, row in events.iterrows():
        sym = row["symbol"]
        ann = row["announce_ts"]
        de = row["delist_ts"]
        entry_target = ann + pd.Timedelta(minutes=ENTRY_OFFSET_MIN)
        exit_target = de - pd.Timedelta(minutes=EXIT_BEFORE_DELIST_MIN)
        if exit_target <= entry_target:
            log.warning("skip %s: exit_target %s <= entry_target %s (gap too small)",
                        sym, exit_target, entry_target)
            skipped += 1
            continue
        df = load_sym_ohlcv(sym)
        if df is None:
            log.warning("skip %s: no OHLCV", sym)
            skipped += 1
            continue
        e = get_close_at_or_after(df, entry_target)
        x = get_close_at_or_before(df, exit_target)
        if e is None or x is None:
            log.warning("skip %s: missing bars (entry=%s exit=%s)", sym, e, x)
            skipped += 1
            continue
        entry_ts, entry_px = e
        exit_ts, exit_px = x
        if exit_ts <= entry_ts:
            log.warning("skip %s: actual exit_ts %s <= entry_ts %s", sym, exit_ts, entry_ts)
            skipped += 1
            continue
        # Hold in days
        hold_days = (exit_ts - entry_ts).total_seconds() / 86400.0
        # Gross returns
        long_gross = (exit_px / entry_px) - 1.0
        short_gross = -long_gross
        out_rows.append({
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
            "quarter": pd.Timestamp(ann).to_period("Q").strftime("%Y-Q%q") if hasattr(pd.Timestamp(ann), "to_period") else str(pd.Timestamp(ann).to_period("Q")),
        })
    log.info("compute_trades: %d valid / %d skipped (of %d events)",
             len(out_rows), skipped, len(events))
    return pd.DataFrame(out_rows)


def build_candidate_pool(trades_df: pd.DataFrame) -> dict[str, np.ndarray]:
    """For fee_aware_perm_test we need candidate pool of GROSS returns over
    non-trigger hold windows with the same direction.

    Use the per-event symbol's OHLCV: for each delisted symbol, generate
    all non-overlapping HOLD_DAYS-day windows in its (announce_ts-1d .. delist_ts+1d)
    range and compute long_gross / short_gross. This forms the null hypothesis:
    "what would the return have been on a random window of the same length in
    the same delisting-week regime?"

    Returns dict {"long": ndarray, "short": ndarray}.
    """
    long_pool = []
    short_pool = []
    for _, row in trades_df.iterrows():
        sym = row["symbol"]
        hold_days = row["hold_days"]
        df = load_sym_ohlcv(sym)
        if df is None:
            continue
        hold_bars = int(hold_days * 1440)  # 1m bars
        if hold_bars < 5:
            continue
        stride = max(1, hold_bars // 3)  # ~3 overlapping windows per real hold to expand pool
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


def three_gate(observed_gross: np.ndarray, candidate_pool: np.ndarray,
               fee: float, hold_days_arr: np.ndarray, label: str) -> dict:
    """Run fee_aware_perm + bootstrap_ci on net (gross - fee) observed returns."""
    obs_net = observed_gross - fee
    fee_res = fee_aware_perm_test(
        observed_net_returns=obs_net,
        candidate_pool_returns=candidate_pool,
        fee_per_trade=fee,
        n_perms=1000,
    )
    # Use block_size=1 because each event is a one-shot symbol-time pair (independent)
    ci_res = bootstrap_ci(obs_net, n_boot=2000, block_size=1)
    gate = {
        "label": label,
        "fee_per_trade": fee,
        "n_obs": int(len(obs_net)),
        "obs_mean_bp": float(obs_net.mean() * 10000) if len(obs_net) else float("nan"),
        "obs_t": fee_res.get("obs_t", float("nan")),
        "null_mean_t": fee_res.get("null_mean_t", float("nan")),
        "signal_t_excess": fee_res.get("signal_t_excess", float("nan")),
        "perm_p_two_sided": fee_res.get("perm_p_two_sided", float("nan")),
        "perm_p_one_sided_above": fee_res.get("perm_p_one_sided_above", float("nan")),
        "perm_p_one_sided_below": fee_res.get("perm_p_one_sided_below", float("nan")),
        "ci_lower_bp": ci_res.get("ci_lower", float("nan")) * 10000 if not math.isnan(ci_res.get("ci_lower", float("nan"))) else float("nan"),
        "ci_upper_bp": ci_res.get("ci_upper", float("nan")) * 10000 if not math.isnan(ci_res.get("ci_upper", float("nan"))) else float("nan"),
        "prob_positive": ci_res.get("prob_positive", float("nan")),
        "n_candidate_pool": int(len(candidate_pool)),
    }
    # Three-gate verdict
    sig_ex = gate["signal_t_excess"]
    ci_lo = gate["ci_lower_bp"]
    pp = gate["perm_p_two_sided"]
    gate["gate_a_sigex_pass"] = (not math.isnan(sig_ex)) and sig_ex >= 2.0
    gate["gate_b_ci_pass"] = (not math.isnan(ci_lo)) and ci_lo > 0
    gate["gate_c_perm_p_pass"] = (not math.isnan(pp)) and pp <= 0.10
    gate["three_gate_pass"] = (gate["gate_a_sigex_pass"] and gate["gate_b_ci_pass"]
                               and gate["gate_c_perm_p_pass"])
    return gate


def concentration(trades_df: pd.DataFrame, side: str, fee: float) -> dict:
    """Concentration diagnostics adapted for one-shot event paradigm."""
    col = f"{side}_gross"
    df = trades_df.copy()
    df["net"] = df[col] - fee
    # per-quarter t-stat
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

    # Per-symbol (each sym = 1 event; CI not bootstrap-able)
    per_sym_records = []
    for sym, sub in df.groupby("symbol"):
        per_sym_records.append({
            "symbol": sym,
            "n_trades": int(len(sub)),
            "mean_bp": float(sub["net"].mean() * 10000),
            "ci_lower_bp": None,  # not applicable (n=1)
            "skip": "n<10_oneshot_event",
        })
    n_sym_measurable = 0  # per-symbol CI not measurable for one-shot
    n_sym_ci_pos = 0

    # Magnitude concentration: top-3 events as % of aggregate mean
    n_total = len(df)
    if n_total == 0:
        top3_pct = float("nan")
    else:
        sorted_net = df["net"].abs().sort_values(ascending=False)
        top3 = float(sorted_net.head(3).sum())
        all_sum = float(sorted_net.sum())
        top3_pct = (top3 / all_sum * 100.0) if all_sum > 0 else float("nan")

    # Sign distribution
    n_pos = int((df["net"] > 0).sum())
    n_neg = int((df["net"] < 0).sum())
    sign_ratio = n_pos / n_total if n_total else float("nan")

    # Concentration Gate verdict
    quarter_pass = (not math.isnan(quarter_pos_t_ratio)) and quarter_pos_t_ratio >= 0.5
    # Symbol axis not applicable; use sign_ratio fallback (>= 50% positive sign)
    sign_pass = (not math.isnan(sign_ratio)) and sign_ratio >= 0.50
    # Single-blowup guard: top-3 absolute magnitude < 40% of total abs sum
    blowup_pass = (not math.isnan(top3_pct)) and top3_pct < 40.0

    return {
        "side": side,
        "per_quarter_t_stats": per_q_records,
        "n_quarters_measurable": n_q_measurable,
        "n_quarters_pos_t": n_q_pos_t,
        "quarter_pos_t_ratio": quarter_pos_t_ratio,
        "per_symbol_records": per_sym_records,
        "n_symbols_measurable": n_sym_measurable,
        "n_symbols_ci_pos": n_sym_ci_pos,
        "symbol_ci_pos_ratio": float("nan"),
        "symbol_axis_note": "one-shot event paradigm: per-symbol n=1, CI not applicable",
        "n_pos": n_pos,
        "n_neg": n_neg,
        "sign_ratio_positive": sign_ratio,
        "top3_abs_concentration_pct": top3_pct,
        "concentration_gate": {
            "quarter_pass": bool(quarter_pass),
            "sign_pass": bool(sign_pass),
            "blowup_pass": bool(blowup_pass),
            "overall_pass": bool(quarter_pass and sign_pass and blowup_pass),
        },
    }


def frequency_first_gate(trades_df: pd.DataFrame, side: str, fee: float) -> dict:
    """4-dim frequency-first gate (life-changing campaign binding)."""
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
    per_trade_net_edge_pct = float(np.median(per_trade_net)) * 100.0  # median per-trade net %

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
        "side": side,
        "fee_per_trade": fee,
        "oos_days": oos_days,
        "n_events": n_events,
        "trades_per_year": trades_per_year,
        "per_trade_net_edge_pct": per_trade_net_edge_pct,
        "capital_utilization_pct": cap_util_pct,
        "mean_hold_days": mean_hold_days,
        "single_trade_sharpe_annualized": single_trade_sharpe_annualized,
        "cutoffs": {
            "trades_per_year": cutoff_trades,
            "per_trade_net_edge_pct": cutoff_edge,
            "capital_utilization_pct": cutoff_util,
            "single_trade_sharpe": cutoff_sharpe,
        },
        "gate_verdict": verdict,
        "fail_dims": fail_dims,
    }


def main():
    log.info("== R-1 binance_delisting_announce_short_alt ==")
    events = load_events()
    log.info("events loaded: %d", len(events))

    trades = compute_trades(events)
    if trades.empty:
        log.error("no valid trades computed -- halt")
        return
    log.info("trades: %d valid", len(trades))
    log.info("gross stats SHORT: mean=%.4f median=%.4f std=%.4f n=%d",
             trades["short_gross"].mean(), trades["short_gross"].median(),
             trades["short_gross"].std(ddof=1), len(trades))
    log.info("gross stats LONG : mean=%.4f median=%.4f std=%.4f n=%d",
             trades["long_gross"].mean(), trades["long_gross"].median(),
             trades["long_gross"].std(ddof=1), len(trades))

    pool = build_candidate_pool(trades)
    log.info("candidate pool: long n=%d, short n=%d", len(pool["long"]), len(pool["short"]))

    # Per quarter sample density check (Lesson #11)
    per_q_counts = trades["quarter"].value_counts().sort_index()
    log.info("per-quarter event counts: %s", per_q_counts.to_dict())

    metrics: dict = {
        "paradigm_name": "binance_delisting_announce_short_alt",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_events": int(len(trades)),
        "n_skipped": int(len(events) - len(trades)),
        "fee_baseline_per_trade": FEE_BASELINE_PER_TRADE,
        "fee_stress_per_trade": FEE_STRESS_PER_TRADE,
        "entry_offset_min": ENTRY_OFFSET_MIN,
        "exit_before_delist_min": EXIT_BEFORE_DELIST_MIN,
        "per_quarter_event_counts": per_q_counts.to_dict(),
        "lesson_11_prescreen": {
            "n_total": int(len(trades)),
            "scope_reduction": "2-quadrant (A focus SHORT + A mirror LONG); B same-sign / B mirror deferred per user authorization (Lesson #11+#19)",
            "concentration_per_quarter_measurable": int((per_q_counts >= 10).sum()),
            "concentration_per_quarter_total": int(len(per_q_counts)),
            "verdict_for_three_gate": "PASS" if len(trades) >= 30 else "FAIL_n_under_30",
            "verdict_for_concentration_quarter": "PASS_at_least_2_quarters_measurable" if (per_q_counts >= 10).sum() >= 2 else "FAIL_under_2_measurable_quarters",
        },
    }

    # === Symmetric Negative Test 2-quadrant: A focus SHORT, A mirror LONG ===
    metrics["symmetric_variants"] = {}
    for label, side in [("A_focus_SHORT", "short"), ("A_mirror_LONG", "long")]:
        log.info("--- %s ---", label)
        observed = trades[f"{side}_gross"].values
        hold_arr = trades["hold_days"].values
        # Baseline fee
        baseline = three_gate(observed, pool[side], FEE_BASELINE_PER_TRADE,
                              hold_arr, f"{label}_fee_baseline")
        # Stress fee
        stress = three_gate(observed, pool[side], FEE_STRESS_PER_TRADE,
                            hold_arr, f"{label}_fee_stress")
        conc_baseline = concentration(trades, side, FEE_BASELINE_PER_TRADE)
        freq_baseline = frequency_first_gate(trades, side, FEE_BASELINE_PER_TRADE)
        freq_stress = frequency_first_gate(trades, side, FEE_STRESS_PER_TRADE)

        # Final verdict
        if baseline["three_gate_pass"] and stress["three_gate_pass"]:
            three_gate_verdict = "PASS_both_fee_levels"
        elif baseline["three_gate_pass"]:
            three_gate_verdict = "FRAGILE_PASS_FEE_SENSITIVE"
        else:
            three_gate_verdict = "FAIL"

        metrics["symmetric_variants"][label] = {
            "side": side,
            "fee_baseline": baseline,
            "fee_stress": stress,
            "concentration_baseline": conc_baseline,
            "frequency_first_gate_baseline": freq_baseline,
            "frequency_first_gate_stress": freq_stress,
            "three_gate_verdict": three_gate_verdict,
            "concentration_gate_overall_pass": conc_baseline["concentration_gate"]["overall_pass"],
            "frequency_gate_baseline_verdict": freq_baseline["gate_verdict"],
            "frequency_gate_stress_verdict": freq_stress["gate_verdict"],
        }
        log.info("  three_gate_verdict=%s, concentration=%s, freq_baseline=%s, freq_stress=%s",
                 three_gate_verdict,
                 conc_baseline["concentration_gate"]["overall_pass"],
                 freq_baseline["gate_verdict"],
                 freq_stress["gate_verdict"])
        log.info("  baseline: obs_t=%.3f, null_mean_t=%.3f, sigex=%.3f, ci=[%.2f, %.2f]bp, perm_p=%.4f",
                 baseline["obs_t"], baseline["null_mean_t"], baseline["signal_t_excess"],
                 baseline["ci_lower_bp"], baseline["ci_upper_bp"], baseline["perm_p_two_sided"])
        log.info("  stress  : obs_t=%.3f, null_mean_t=%.3f, sigex=%.3f, ci=[%.2f, %.2f]bp, perm_p=%.4f",
                 stress["obs_t"], stress["null_mean_t"], stress["signal_t_excess"],
                 stress["ci_lower_bp"], stress["ci_upper_bp"], stress["perm_p_two_sided"])
        log.info("  freq_baseline: trades/yr=%.1f, edge=%.2f%%, util=%.1f%%, sharpe=%.2f",
                 freq_baseline.get("trades_per_year", float("nan")),
                 freq_baseline.get("per_trade_net_edge_pct", float("nan")),
                 freq_baseline.get("capital_utilization_pct", float("nan")),
                 freq_baseline.get("single_trade_sharpe_annualized", float("nan")))

    # === Final overall verdict logic ===
    a_focus = metrics["symmetric_variants"]["A_focus_SHORT"]
    a_mirror = metrics["symmetric_variants"]["A_mirror_LONG"]
    # Broad-falsified test: both 3-gate FAIL
    if (not a_focus["fee_baseline"]["three_gate_pass"]) and (not a_mirror["fee_baseline"]["three_gate_pass"]):
        overall = "BROAD_FALSIFIED_2Q"
    elif a_focus["fee_baseline"]["three_gate_pass"] and not a_focus["concentration_gate_overall_pass"]:
        overall = "CONCENTRATED_R1_PASS"
    elif a_focus["fee_baseline"]["three_gate_pass"] and not a_focus["fee_stress"]["three_gate_pass"]:
        overall = "FRAGILE_PASS_FEE_SENSITIVE"
    elif a_focus["fee_baseline"]["three_gate_pass"]:
        if a_focus["frequency_gate_baseline_verdict"] == "PASS":
            overall = "PASS_R1_FULL"
        else:
            overall = "PASS_R1_THREE_GATE_BUT_FREQUENCY_FAIL"
    else:
        overall = "FAIL_OTHER"
    metrics["overall_verdict"] = overall

    OUT_JSON.write_text(json.dumps(metrics, default=str, indent=2))
    log.info("wrote %s", OUT_JSON)
    log.info("=== OVERALL VERDICT: %s ===", overall)


if __name__ == "__main__":
    main()
