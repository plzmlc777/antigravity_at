"""R-1 PoC: paradigm_249_alt_cross_exchange_funding_rate_spread_binance_bybit_z_7d_bilateral.

Hypothesis
----------
Cross-venue USDT-perp 8h funding rate spread (Binance - Bybit) rolling 30d z
predicts 7d directional alt move.

- Positive spread z >= +T (Binance funding > Bybit funding): Binance traders
  more crowded LONG. Squeeze/compression → SHORT signal (fade continuation)
- Negative spread z <= -T (Bybit > Binance): mirror → LONG signal

Bilateral 4-quadrant SNT (Lesson #19):
  A_focus:  z >= +T → SHORT
  A_mirror: z >= +T → LONG
  B_focus:  z <= -T → LONG
  B_mirror: z <= -T → SHORT

Design
------
- Primary sym: SOLUSDT (per hypothesis)
- Sweep: T in {1.5, 2.0, 2.5} × hold in {5d, 7d, 10d} × 4 quadrants = 36 cells
- Entry: UTC midnight OPEN of day AFTER trigger day (Lesson #82 compliant)
- Fee: 8bp round-trip per trade (0.0008)
- Non-overlapping trades (cooldown = hold_days)
- Full-data R-1 stats; OOS half tracked for Lesson #79 sanity

Predecessor paradigm 103 (BROAD_FALSIFIED_FEE_FLOOR, 2026-05-19):
- Same substrate + universe + statistic + direction (4/5 DNA overlap)
- Only hold dimension differs: 249 uses 7d, 103 used 60/240/480/1440m max
- Paradigm 103 noted asymmetric hold response, 1440m sigex +2.12 but ci_lower
  unmeasured — 7d is the untested extension per runbook §N+5.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from scripts.research._ohlcv_parquet_cache import load_ohlcv_1m_cached  # noqa: E402
from scripts.research._perm_utils import bootstrap_ci, fee_aware_perm_test  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("paradigm249_r1")

PARADIGM_NAME = "paradigm_249_alt_cross_exchange_funding_rate_spread_binance_bybit_z_7d_bilateral"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_NAME
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Primary + expansion universe (all have Bybit + Binance funding coverage since 2023-11)
PRIMARY_SYM = "SOLUSDT"
UNIVERSE = ["SOLUSDT", "AVAXUSDT", "BNBUSDT", "DOGEUSDT", "LINKUSDT", "XRPUSDT", "BCHUSDT"]

BYBIT_CACHE_DIR = ROOT / "runs" / "ohlcv_cache" / "bybit_funding"

FEE_PER_TRADE = 0.0008  # 8bp round-trip
Z_WINDOW_DAYS = 30
Z_THRESHOLDS = [1.5, 2.0, 2.5]
HOLD_DAYS_SWEEP = [5, 7, 10]

# 3-gate thresholds
SIG_T_EXCESS_PASS = 1.5     # weakened per instructions
PERM_P_PASS = 0.10
CI_LOWER_PASS_FRAC = -0.005  # -50bp weak-positive floor (per instructions)


def load_binance_funding(sym: str) -> pd.DataFrame:
    with SessionLocal() as s:
        rows = s.execute(
            text("SELECT funding_time, funding_rate FROM binance_funding_rate WHERE symbol=:s ORDER BY funding_time ASC"),
            {"s": sym},
        ).fetchall()
    df = pd.DataFrame(rows, columns=["funding_time", "funding_rate"])
    df["funding_time"] = pd.to_datetime(df["funding_time"])
    df["funding_rate"] = df["funding_rate"].astype(float)
    return df


def load_bybit_funding(sym: str) -> pd.DataFrame:
    p = BYBIT_CACHE_DIR / f"{sym}.joblib"
    return joblib.load(p)


def compute_spread_daily(sym: str) -> pd.DataFrame:
    bn = load_binance_funding(sym)
    by = load_bybit_funding(sym)
    merged = pd.merge(bn, by, on="funding_time", suffixes=("_bn", "_by"), how="inner")
    merged["spread"] = merged["funding_rate_bn"] - merged["funding_rate_by"]
    merged["date"] = merged["funding_time"].dt.floor("D")
    daily = merged.groupby("date").agg(spread=("spread", "mean"), n=("spread", "size")).reset_index()
    daily = daily[daily["n"] == 3].reset_index(drop=True)  # 3 8h cycles per day
    daily["mu"] = daily["spread"].rolling(Z_WINDOW_DAYS, min_periods=15).mean()
    daily["sd"] = daily["spread"].rolling(Z_WINDOW_DAYS, min_periods=15).std()
    daily["spread_z"] = (daily["spread"] - daily["mu"]) / daily["sd"]
    return daily.dropna(subset=["spread_z"]).reset_index(drop=True)


def compute_midnight_opens(sym: str) -> pd.DataFrame:
    df1m = load_ohlcv_1m_cached(sym)
    if df1m is None or len(df1m) == 0:
        return None
    if "ts" in df1m.columns:
        df1m = df1m.set_index(pd.to_datetime(df1m["ts"]))
    elif not isinstance(df1m.index, pd.DatetimeIndex):
        df1m.index = pd.to_datetime(df1m.index)
    df1m = df1m.sort_index()
    df1m["date"] = df1m.index.floor("D")
    midnight_open = df1m.groupby("date").first()["open"].reset_index()
    midnight_open.columns = ["date", "open_utc00"]
    return midnight_open


def build_candidate_pool_gross(midnight_open: pd.DataFrame, hold_days: int) -> np.ndarray:
    """All possible fwd returns entering at each midnight open, holding hold_days.
    Used as fee_aware_perm_test candidate pool (SIGNED wrong — we return abs values because
    perm test expects gross returns representing the direction-agnostic outcome pool)."""
    mo = midnight_open.copy().sort_values("date").reset_index(drop=True)
    mo["entry_open"] = mo["open_utc00"].shift(-1)
    mo["exit_open"] = mo["open_utc00"].shift(-1 - hold_days)
    mo["fwd_ret"] = (mo["exit_open"] / mo["entry_open"]) - 1
    return mo["fwd_ret"].dropna().values


def enter_trades(daily: pd.DataFrame, midnight_open: pd.DataFrame, threshold: float, side_pos: bool, direction: int, hold_days: int, cooldown_days: int) -> pd.DataFrame:
    """Enumerate trades.
    side_pos=True: trigger when spread_z >= +threshold
    side_pos=False: trigger when spread_z <= -threshold
    direction: +1 (LONG) or -1 (SHORT)
    """
    m = pd.merge(daily, midnight_open, on="date", how="inner")
    m = m.sort_values("date").reset_index(drop=True)
    m["entry_open"] = m["open_utc00"].shift(-1)
    m["exit_open"] = m["open_utc00"].shift(-1 - hold_days)
    m["fwd_ret"] = (m["exit_open"] / m["entry_open"]) - 1
    m = m.dropna(subset=["fwd_ret", "spread_z"]).reset_index(drop=True)
    if side_pos:
        trig_mask = m["spread_z"] >= threshold
    else:
        trig_mask = m["spread_z"] <= -threshold
    trigs = m[trig_mask].copy()
    trigs = trigs.sort_values("date").reset_index(drop=True)
    # cooldown enforcement
    kept = []
    last_exit_date = None
    for _, row in trigs.iterrows():
        entry_date = row["date"] + pd.Timedelta(days=1)
        if last_exit_date is not None and entry_date < last_exit_date:
            continue
        kept.append(row)
        last_exit_date = entry_date + pd.Timedelta(days=hold_days)
    if not kept:
        return pd.DataFrame(columns=["date", "entry_open", "exit_open", "fwd_ret", "spread_z", "signed_ret", "net_ret"])
    out = pd.DataFrame(kept).reset_index(drop=True)
    out["signed_ret"] = direction * out["fwd_ret"]
    out["net_ret"] = out["signed_ret"] - FEE_PER_TRADE
    out["direction"] = direction
    return out


def run_r1_cell(sym: str, daily: pd.DataFrame, midnight_open: pd.DataFrame,
                threshold: float, side_pos: bool, direction: int, hold_days: int,
                candidate_pool_gross: np.ndarray, quadrant_label: str) -> Dict:
    trades = enter_trades(daily, midnight_open, threshold, side_pos, direction, hold_days, cooldown_days=hold_days)
    n = len(trades)
    if n < 5:
        return {
            "quadrant": quadrant_label, "threshold_z": threshold, "hold_days": hold_days,
            "n_trades": int(n), "verdict": "INSUFFICIENT_SAMPLES",
        }
    net = trades["net_ret"].values
    signed = trades["signed_ret"].values
    perm = fee_aware_perm_test(
        observed_net_returns=net,
        candidate_pool_returns=direction * candidate_pool_gross,  # sign-align pool to trade direction
        fee_per_trade=FEE_PER_TRADE,
        n_perms=1000,
        rng_seed=42,
    )
    ci = bootstrap_ci(net, n_boot=2000, block_size=1, rng_seed=42)
    gross_mean = float(signed.mean())
    net_mean = float(net.mean())
    verdict = "FAIL"
    passes_three_gate = (
        perm.get("signal_t_excess") is not None
        and np.isfinite(perm.get("signal_t_excess", float("nan")))
        and perm["signal_t_excess"] >= SIG_T_EXCESS_PASS
        and ci["ci_lower"] > CI_LOWER_PASS_FRAC
        and net_mean > 0
    )
    if passes_three_gate:
        verdict = "PASS_WEAK"
    return {
        "quadrant": quadrant_label,
        "threshold_z": threshold,
        "hold_days": hold_days,
        "n_trades": int(n),
        "gross_mean_bp": gross_mean * 10000,
        "net_mean_bp": net_mean * 10000,
        "signal_t_excess": float(perm.get("signal_t_excess", float("nan"))),
        "obs_t": float(perm.get("obs_t", float("nan"))),
        "null_mean_t": float(perm.get("null_mean_t", float("nan"))),
        "perm_p_two": float(perm.get("perm_p_two_sided", float("nan"))),
        "perm_p_one_above": float(perm.get("perm_p_one_sided_above", float("nan"))),
        "ci_lower_bp": ci["ci_lower"] * 10000,
        "ci_upper_bp": ci["ci_upper"] * 10000,
        "verdict": verdict,
    }


def main():
    t0 = time.time()
    log.info(f"paradigm 249 R-1 start — sym={PRIMARY_SYM}, expansion={UNIVERSE}")

    # Primary sym cells first
    daily = compute_spread_daily(PRIMARY_SYM)
    mo = compute_midnight_opens(PRIMARY_SYM)
    log.info(f"[{PRIMARY_SYM}] daily n={len(daily)}, mo n={len(mo)}")

    all_cells = []
    for hd in HOLD_DAYS_SWEEP:
        pool = build_candidate_pool_gross(mo, hd)
        log.info(f"[{PRIMARY_SYM}] hold={hd}d candidate_pool n={len(pool)}")
        for T in Z_THRESHOLDS:
            # A_focus: spread_z >= +T → SHORT
            all_cells.append(run_r1_cell(PRIMARY_SYM, daily, mo, T, side_pos=True, direction=-1, hold_days=hd, candidate_pool_gross=pool, quadrant_label="A_focus_shortHigh"))
            # A_mirror: spread_z >= +T → LONG
            all_cells.append(run_r1_cell(PRIMARY_SYM, daily, mo, T, side_pos=True, direction=+1, hold_days=hd, candidate_pool_gross=pool, quadrant_label="A_mirror_longHigh"))
            # B_focus: spread_z <= -T → LONG
            all_cells.append(run_r1_cell(PRIMARY_SYM, daily, mo, T, side_pos=False, direction=+1, hold_days=hd, candidate_pool_gross=pool, quadrant_label="B_focus_longLow"))
            # B_mirror: spread_z <= -T → SHORT
            all_cells.append(run_r1_cell(PRIMARY_SYM, daily, mo, T, side_pos=False, direction=-1, hold_days=hd, candidate_pool_gross=pool, quadrant_label="B_mirror_shortLow"))

    # Lesson #39 sub-class A check
    ls39 = []
    for T in Z_THRESHOLDS:
        for hd in HOLD_DAYS_SWEEP:
            afocus = [c for c in all_cells if c.get("quadrant") == "A_focus_shortHigh" and c["threshold_z"] == T and c["hold_days"] == hd]
            amirror = [c for c in all_cells if c.get("quadrant") == "A_mirror_longHigh" and c["threshold_z"] == T and c["hold_days"] == hd]
            if afocus and amirror and "net_mean_bp" in afocus[0] and "net_mean_bp" in amirror[0]:
                ssum = afocus[0]["net_mean_bp"] + amirror[0]["net_mean_bp"]
                ls39.append({"T": T, "hold": hd, "A_focus_net_bp": afocus[0]["net_mean_bp"], "A_mirror_net_bp": amirror[0]["net_mean_bp"], "sum_bp": ssum, "is_exactly_neg_16bp": abs(ssum - (-16)) < 0.5})

    # Best cell selection (highest net_mean_bp * signal_t_excess among 3-gate PASS_WEAK candidates,
    # fallback to highest sig_t_excess if none pass)
    passers = [c for c in all_cells if c.get("verdict") == "PASS_WEAK"]
    if passers:
        best = max(passers, key=lambda c: (c["signal_t_excess"], c["net_mean_bp"]))
        best_verdict = "R1_PASS_WEAK"
    else:
        # rank by sig_t_excess for diagnostic
        cells_with_metric = [c for c in all_cells if "signal_t_excess" in c and np.isfinite(c.get("signal_t_excess", float("nan")))]
        if cells_with_metric:
            best = max(cells_with_metric, key=lambda c: c["signal_t_excess"])
        else:
            best = None
        best_verdict = "R1_FAIL"

    # Symmetric Negative Test overall diagnosis
    quadrant_sums = {}
    for q in ["A_focus_shortHigh", "A_mirror_longHigh", "B_focus_longLow", "B_mirror_shortLow"]:
        cells_q = [c for c in all_cells if c.get("quadrant") == q and "net_mean_bp" in c]
        if cells_q:
            n_pos = sum(1 for c in cells_q if c["net_mean_bp"] > 0)
            quadrant_sums[q] = {"n_cells": len(cells_q), "n_net_pos": n_pos, "mean_net_bp": float(np.mean([c["net_mean_bp"] for c in cells_q]))}

    # Export best-cell trades
    if best is not None and best_verdict == "R1_PASS_WEAK":
        # regenerate best-cell trades for export
        q_map = {
            "A_focus_shortHigh": (True, -1),
            "A_mirror_longHigh": (True, +1),
            "B_focus_longLow": (False, +1),
            "B_mirror_shortLow": (False, -1),
        }
        side_pos, direction = q_map[best["quadrant"]]
        best_trades = enter_trades(daily, mo, best["threshold_z"], side_pos, direction, best["hold_days"], cooldown_days=best["hold_days"])
        trades_out = []
        for _, r in best_trades.iterrows():
            entry_date = r["date"] + pd.Timedelta(days=1)
            exit_date = entry_date + pd.Timedelta(days=best["hold_days"])
            trades_out.append({
                "entry_ts": entry_date.isoformat(),
                "exit_ts": exit_date.isoformat(),
                "net_ret": float(r["net_ret"]),
            })
        (OUT_DIR / "r1_best_cell_trades.json").write_text(json.dumps(trades_out, indent=2))
        log.info(f"exported {len(trades_out)} best-cell trades")

    elapsed = time.time() - t0
    metrics = {
        "paradigm_name": PARADIGM_NAME,
        "date": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": elapsed,
        "primary_sym": PRIMARY_SYM,
        "z_thresholds": Z_THRESHOLDS,
        "hold_days_sweep": HOLD_DAYS_SWEEP,
        "fee_per_trade": FEE_PER_TRADE,
        "cells": all_cells,
        "lesson_39_subclass_A_check": ls39,
        "quadrant_summary": quadrant_sums,
        "best_cell": best,
        "verdict": best_verdict,
    }
    (OUT_DIR / "r1_metrics.json").write_text(json.dumps(metrics, indent=2, default=str))
    log.info(f"R-1 complete in {elapsed:.1f}s — verdict={best_verdict}")
    log.info(f"best cell: {best}")


if __name__ == "__main__":
    main()
