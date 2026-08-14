"""R-1 PoC — paradigm 233 alt_toptrader_position_lsr_velocity_z_bilateral_4h.

Hypothesis: velocity (1st-derivative rolling z) of `toptrader_position_ls_ratio`
(POSITION-notional-value weighted long/short ratio) detects rapid large-capital
repositioning. Direction FOLLOW: rising position-LSR = smart money net-long
build-up -> LONG signal.

DIFFERENTIATORS vs graveyard `smart_money_lsr_contrarian`:
  - column: toptrader_POSITION_ls_ratio (notional) vs graveyard's toptrader_ACCOUNT_ls_ratio (count). corr(SOL)=0.19.
  - statistic: velocity z (1st derivative) vs graveyard level z
  - direction: FOLLOW velocity vs graveyard CONTRARIAN level

Lesson #37 compliance: full hold x threshold x window sweep; verdict scan across
ALL cells, not primary only.

Lesson #19 compliance: joint-trigger 4-quadrant Symmetric Negative Test (SNT):
  - A_focus  : LONG  when vel_z > +T  (rising smart-money long bias -> follow)
  - A_mirror : SHORT when vel_z > +T  (mirror sign flip)
  - B_focus  : SHORT when vel_z < -T  (rising smart-money short bias -> follow)
  - B_mirror : LONG  when vel_z < -T  (mirror sign flip)

Lesson #39 sub-class A check: direction from vel_z sign (microstructure-derived),
NOT from bar_direction. A_focus + A_mirror should NOT equal -16bp (2x fee) if
signal has real content.

Single symbol R-1: SOLUSDT.

Output: backend/runs/research_track/paradigm_233_alt_toptrader_position_lsr_velocity_z_bilateral_4h/r1__metrics.json
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from itertools import product
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("paradigm_233_r1")

PARADIGM = "paradigm_233_alt_toptrader_position_lsr_velocity_z_bilateral_4h"
JOBLIB_DIR = ROOT / "runs" / "microstructure"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Constants
FEE_RATE = 0.0004           # Binance taker per side (round trip 8 bps)
CAPITAL = 1_000_000.0
TRAIN_FRAC = 0.5            # last 50% OOS

R1_SYMBOL = "SOLUSDT"
VELOCITY_WINDOW_GRID = [144, 288, 576]   # 12h / 24h / 48h on 5m bars
VELOCITY_Z_GRID = [1.0, 1.5, 2.0]
HOLD_GRID = [12, 48, 96]                 # 1h / 4h / 8h on 5m bars
QUADRANTS = ["A_focus", "A_mirror", "B_focus", "B_mirror"]


def load_panel(symbol: str, velocity_window: int) -> pd.DataFrame:
    path = JOBLIB_DIR / f"{symbol}_full_metrics.joblib"
    df = joblib.load(path)
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="first")]
    df["price"] = df["open_interest_value_usdt"] / df["open_interest"]
    df["pos_lsr"] = df["toptrader_position_ls_ratio"]
    df = df.dropna(subset=["price", "pos_lsr"])
    # velocity = 1st derivative of position LSR
    df["pos_lsr_vel"] = df["pos_lsr"].diff(1)
    # z-score of velocity series over rolling window
    vel_mean = df["pos_lsr_vel"].rolling(velocity_window, min_periods=velocity_window // 2).mean()
    vel_std = df["pos_lsr_vel"].rolling(velocity_window, min_periods=velocity_window // 2).std()
    df["vel_z"] = (df["pos_lsr_vel"] - vel_mean) / vel_std.replace(0, np.nan)
    df["vel_z"] = df["vel_z"].replace([np.inf, -np.inf], np.nan)
    return df


def simulate_quadrant(
    df: pd.DataFrame,
    quadrant: str,
    entry_z: float,
    max_hold_bars: int,
    velocity_window: int,
    fee_rate: float = FEE_RATE,
) -> dict:
    """Fixed-hold sim (no SL, no exit-signal): enter on trigger, hold N bars, close.

    Quadrant semantics:
      A_focus  : entry when vel_z >= +entry_z, direction = +1 (LONG)
      A_mirror : entry when vel_z >= +entry_z, direction = -1 (SHORT)
      B_focus  : entry when vel_z <= -entry_z, direction = -1 (SHORT)
      B_mirror : entry when vel_z <= -entry_z, direction = +1 (LONG)

    Non-overlapping: after entry, skip max_hold_bars before considering next entry.
    """
    px = df["price"].to_numpy()
    z = df["vel_z"].to_numpy()
    n = len(df)
    if n < velocity_window + max_hold_bars + 100:
        return _empty_metrics()

    trades = []
    i = velocity_window
    while i < n - max_hold_bars - 1:
        zi = z[i]
        if not np.isfinite(zi):
            i += 1
            continue

        triggered = False
        direction = 0

        if quadrant == "A_focus" and zi >= entry_z:
            triggered = True
            direction = +1
        elif quadrant == "A_mirror" and zi >= entry_z:
            triggered = True
            direction = -1
        elif quadrant == "B_focus" and zi <= -entry_z:
            triggered = True
            direction = -1
        elif quadrant == "B_mirror" and zi <= -entry_z:
            triggered = True
            direction = +1

        if not triggered:
            i += 1
            continue

        entry_idx = i
        exit_idx = min(i + max_hold_bars, n - 1)
        entry_px = px[entry_idx]
        exit_px = px[exit_idx]
        if entry_px <= 0:
            i += 1
            continue
        gross_ret = direction * (exit_px / entry_px - 1.0)
        fee = 2 * fee_rate  # round-trip
        net_ret = gross_ret - fee
        trades.append({
            "entry_idx": int(entry_idx),
            "exit_idx": int(exit_idx),
            "direction": int(direction),
            "gross_ret": float(gross_ret),
            "net_ret": float(net_ret),
            "vel_z_at_entry": float(zi),
        })
        i = exit_idx + 1  # non-overlapping

    if not trades:
        return _empty_metrics()

    net_rets = np.array([t["net_ret"] for t in trades])
    gross_rets = np.array([t["gross_ret"] for t in trades])
    total_return = float(np.prod(1 + net_rets) - 1.0)
    bh_return = float(px[-1] / px[velocity_window] - 1.0)
    alpha = total_return - bh_return
    wins = int((net_rets > 0).sum())
    n_trades = len(trades)
    win_rate = wins / n_trades * 100
    mean_net_ret_bp = float(net_rets.mean() * 10000)
    mean_gross_ret_bp = float(gross_rets.mean() * 10000)
    median_net_ret_bp = float(np.median(net_rets) * 10000)

    if len(net_rets) > 1 and net_rets.std() > 0:
        # per-trade sharpe; annualize by trades/yr
        bars_per_yr = 12 * 24 * 365
        oos_bars = df.shape[0] - velocity_window
        trades_per_yr = n_trades / (oos_bars / bars_per_yr) if oos_bars > 0 else 0.0
        sharpe = net_rets.mean() / net_rets.std() * np.sqrt(max(trades_per_yr, 1))
    else:
        sharpe = 0.0
        trades_per_yr = 0.0

    # rolling equity for max_dd
    eq = np.cumprod(1 + net_rets) * CAPITAL
    cummax = np.maximum.accumulate(eq)
    max_dd_pct = float(abs(((eq / cummax) - 1.0).min()) * 100)

    pf = (net_rets[net_rets > 0].sum() / -net_rets[net_rets < 0].sum()) if (net_rets < 0).any() else 999.0

    return {
        "n_trades": n_trades,
        "alpha_pct": float(alpha * 100),
        "total_return_pct": float(total_return * 100),
        "buy_hold_pct": float(bh_return * 100),
        "sharpe_ann": float(sharpe),
        "trades_per_yr": float(trades_per_yr),
        "max_dd_pct": max_dd_pct,
        "win_rate_pct": float(win_rate),
        "profit_factor": float(pf),
        "mean_net_ret_bp": mean_net_ret_bp,
        "mean_gross_ret_bp": mean_gross_ret_bp,
        "median_net_ret_bp": median_net_ret_bp,
    }


def _empty_metrics() -> dict:
    return {
        "n_trades": 0, "alpha_pct": 0.0, "total_return_pct": 0.0, "buy_hold_pct": 0.0,
        "sharpe_ann": 0.0, "trades_per_yr": 0.0, "max_dd_pct": 0.0,
        "win_rate_pct": 0.0, "profit_factor": 0.0,
        "mean_net_ret_bp": 0.0, "mean_gross_ret_bp": 0.0, "median_net_ret_bp": 0.0,
    }


def main() -> int:
    log.info("paradigm 233 R-1 dispatch starting: symbol=%s", R1_SYMBOL)

    # cache panels by velocity_window
    panels: dict[int, pd.DataFrame] = {}
    for vw in VELOCITY_WINDOW_GRID:
        log.info("loading panel vw=%d ...", vw)
        panels[vw] = load_panel(R1_SYMBOL, vw)
        log.info("  vw=%d rows=%d range=%s..%s", vw, len(panels[vw]),
                 panels[vw].index.min(), panels[vw].index.max())

    results: list[dict] = []
    for vw, ez, hold, quad in product(VELOCITY_WINDOW_GRID, VELOCITY_Z_GRID, HOLD_GRID, QUADRANTS):
        df_full = panels[vw]
        split_idx = int(len(df_full) * TRAIN_FRAC)
        df_oos = df_full.iloc[split_idx:].copy()
        spec = f"vw{vw}_ez{ez}_h{hold}_{quad}"
        m = simulate_quadrant(df_oos, quad, ez, hold, vw)
        m["spec"] = spec
        m["velocity_window"] = vw
        m["entry_z"] = ez
        m["hold_bars"] = hold
        m["quadrant"] = quad
        results.append(m)
        log.info("  %s -> trades=%d alpha=%.2f%% sharpe=%.2f wr=%.1f%% mean_net_bp=%.1f",
                 spec, m["n_trades"], m["alpha_pct"], m["sharpe_ann"],
                 m["win_rate_pct"], m["mean_net_ret_bp"])

    # Lesson #39 sub-class A check: for each (vw, ez, hold), sum of A_focus and A_mirror mean_net_ret_bp
    lesson_39_checks = []
    for vw, ez, hold in product(VELOCITY_WINDOW_GRID, VELOCITY_Z_GRID, HOLD_GRID):
        a_focus = next((r for r in results if r["velocity_window"] == vw and r["entry_z"] == ez
                        and r["hold_bars"] == hold and r["quadrant"] == "A_focus"), None)
        a_mirror = next((r for r in results if r["velocity_window"] == vw and r["entry_z"] == ez
                         and r["hold_bars"] == hold and r["quadrant"] == "A_mirror"), None)
        b_focus = next((r for r in results if r["velocity_window"] == vw and r["entry_z"] == ez
                        and r["hold_bars"] == hold and r["quadrant"] == "B_focus"), None)
        b_mirror = next((r for r in results if r["velocity_window"] == vw and r["entry_z"] == ez
                         and r["hold_bars"] == hold and r["quadrant"] == "B_mirror"), None)
        if a_focus and a_mirror and b_focus and b_mirror:
            a_sum_bp = a_focus["mean_net_ret_bp"] + a_mirror["mean_net_ret_bp"]
            b_sum_bp = b_focus["mean_net_ret_bp"] + b_mirror["mean_net_ret_bp"]
            lesson_39_checks.append({
                "cell": f"vw{vw}_ez{ez}_h{hold}",
                "A_sum_bp": round(a_sum_bp, 2),
                "B_sum_bp": round(b_sum_bp, 2),
                "A_looks_fee_symmetric": bool(abs(a_sum_bp + 16.0) < 4.0),  # ~-16bp
                "B_looks_fee_symmetric": bool(abs(b_sum_bp + 16.0) < 4.0),
                "A_focus_alpha_pct": a_focus["alpha_pct"],
                "A_mirror_alpha_pct": a_mirror["alpha_pct"],
                "B_focus_alpha_pct": b_focus["alpha_pct"],
                "B_mirror_alpha_pct": b_mirror["alpha_pct"],
                "A_focus_n": a_focus["n_trades"],
                "B_focus_n": b_focus["n_trades"],
            })

    # Full sweep verdict scan (Lesson #37): find best PASS cells
    def cell_passes(r: dict) -> bool:
        return (r["n_trades"] >= 30
                and r["alpha_pct"] > 0
                and r["sharpe_ann"] > 0
                and r["mean_net_ret_bp"] > 0)

    focus_results = [r for r in results if r["quadrant"] in ("A_focus", "B_focus")]
    mirror_results = [r for r in results if r["quadrant"] in ("A_mirror", "B_mirror")]
    passing_focus = [r for r in focus_results if cell_passes(r)]
    passing_mirror = [r for r in mirror_results if cell_passes(r)]

    best_focus = max(focus_results, key=lambda r: r["alpha_pct"]) if focus_results else None
    best_a_focus = max([r for r in results if r["quadrant"] == "A_focus"],
                       key=lambda r: r["alpha_pct"], default=None)
    best_b_focus = max([r for r in results if r["quadrant"] == "B_focus"],
                       key=lambda r: r["alpha_pct"], default=None)

    # Fail-fast: if ALL focus cells (both directions) have alpha <= 0 AND sharpe <= 0
    focus_any_positive = any(r["alpha_pct"] > 0 or r["sharpe_ann"] > 0 for r in focus_results)

    # Lesson #39 antipattern detection
    lesson_39_all_fee_symmetric = (
        len(lesson_39_checks) > 0 and
        all(c["A_looks_fee_symmetric"] and c["B_looks_fee_symmetric"] for c in lesson_39_checks)
    )
    lesson_39_majority_fee_symmetric = (
        len(lesson_39_checks) > 0 and
        (sum(1 for c in lesson_39_checks if c["A_looks_fee_symmetric"]) >= len(lesson_39_checks) * 0.7)
    )

    # Verdict
    verdict = "FAIL"
    reason = ""
    if not focus_any_positive:
        reason = "no focus cell (A_focus or B_focus) shows alpha>0 or sharpe>0 across full sweep"
        verdict = "FAIL_FAIL_FAST"
    elif lesson_39_all_fee_symmetric:
        reason = "Lesson #39 sub-class A antipattern: A_focus+A_mirror ~= -16bp (fee-symmetric) in ALL cells"
        verdict = "FAIL_LESSON_39_SUBCLASS_A"
    elif len(passing_focus) == 0:
        reason = f"no focus cell passes 3-gate (alpha>0, sharpe>0, mean_net_bp>0, n>=30). best_focus alpha={best_focus['alpha_pct']:.2f}%"
        verdict = "FAIL"
    else:
        best_passing = max(passing_focus, key=lambda r: r["alpha_pct"])
        reason = (f"{len(passing_focus)} focus cells pass; best={best_passing['spec']} "
                  f"alpha={best_passing['alpha_pct']:.2f}% sharpe={best_passing['sharpe_ann']:.2f}")
        verdict = "PASS"

    out = {
        "paradigm": PARADIGM,
        "phase": "R-1_PoC",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "symbol": R1_SYMBOL,
            "velocity_window_grid": VELOCITY_WINDOW_GRID,
            "velocity_z_grid": VELOCITY_Z_GRID,
            "hold_grid_bars": HOLD_GRID,
            "quadrants": QUADRANTS,
            "fee_rate_per_side": FEE_RATE,
            "capital": CAPITAL,
            "train_frac": TRAIN_FRAC,
            "signal_column": "toptrader_position_ls_ratio",
            "signal_transform": "velocity_z (1st_derivative_rolling_z)",
        },
        "all_specs": results,
        "lesson_39_symmetric_checks": lesson_39_checks,
        "lesson_39_all_fee_symmetric": lesson_39_all_fee_symmetric,
        "lesson_39_majority_fee_symmetric": lesson_39_majority_fee_symmetric,
        "n_focus_passing": len(passing_focus),
        "n_mirror_passing": len(passing_mirror),
        "best_focus_cell": best_focus,
        "best_A_focus": best_a_focus,
        "best_B_focus": best_b_focus,
        "verdict": verdict,
        "fail_fast_reason": reason,
        "next_phase": "R-2" if verdict == "PASS" else "graveyard",
    }

    out_path = OUT_DIR / "r1__metrics.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    log.info("wrote %s", out_path)
    log.info("VERDICT=%s reason=%s", verdict, reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
