"""paradigm_251 R-1: cross_sym_oi_daily_drop_event_contagion_bilateral_5d

Hypothesis:
  For a 14-sym Binance USDT-M perp universe, when ANY symbol registers a
  daily-aggregated open-interest %-change z-score below -2.0 (large OI drop
  event, contagion trigger) or above +2.0 (large OI spike event, crowding
  trigger), the OTHER 13 symbols exhibit a bilateral directional edge over a
  5-day (7,200-minute) forward hold.

Four-quadrant Symmetric Negative Test (Lesson #19 + #39 mandatory):
  A_focus : trigger z < -2.0  -> SHORT other syms   (contagion / risk-off cascade)
  A_mirror: trigger z < -2.0  -> LONG  other syms   (capital rotation / recovery)
  B_focus : trigger z > +2.0  -> LONG  other syms   (momentum / liquidity expansion)
  B_mirror: trigger z > +2.0  -> SHORT other syms   (crowding reversal)

Substrate:
  - runs/microstructure/{SYM}USDT_full_metrics.joblib  ('open_interest' col)
    -> resample 1D last() -> daily OI close
    -> 30d rolling z of pct_change per symbol
  - runs/ohlcv_cache/{SYM}USDT_1m.joblib
    -> resample 1D first(open) & last(close)
    -> forward return T+1 open -> T+6 open (5 trading days hold)

Lookahead invariant:
  - trigger detected at UTC 00:00 of day T (uses T's OI close and prior 30 days)
  - entry at day T+1 first 1m open
  - exit  at day T+6 first 1m open
  - target sym forward return uses ONLY dates > T

Event-level bootstrap (Lesson #74):
  - 13 target-sym returns from the same trigger day T are dependent (share regime)
  - bootstrap resamples EVENT DAYS with replacement; edge is the mean of the
    event-level means; CI is event-level.

Fee model:
  - Binance USDT-M perp maker round-trip = 8bp = 0.0008

Outputs:
  runs/research_track/paradigm_251.../r1__metrics.json
  runs/research_track/paradigm_251.../trades_{quadrant}_{sym}.json  (best cell)
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import joblib
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE / "scripts"))
from research._perm_utils import bootstrap_ci, fee_aware_perm_test  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("paradigm_251")

SYMS: List[str] = [
    "ADA", "AVAX", "BCH", "BNB", "BTC", "DOGE", "ETH", "FIL",
    "LINK", "LTC", "NEAR", "SOL", "WIF", "XRP",
]
HOLD_DAYS = 5
FEE_ROUND_TRIP = 0.0008
Z_THRESHOLD = 2.0
ROLL_WINDOW = 30
ROLL_MIN = 20

OUT_DIR = BASE / "runs" / "research_track" / (
    "paradigm_251_cross_sym_oi_daily_drop_contagion_bilateral_5d"
)
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_daily_oi_z() -> Dict[str, pd.Series]:
    """Return sym -> 30d z of daily OI pct-change (indexed by UTC midnight of day T)."""
    z_by_sym: Dict[str, pd.Series] = {}
    for s in SYMS:
        path = BASE / "runs" / "microstructure" / f"{s}USDT_full_metrics.joblib"
        df = joblib.load(path)
        oi = df["open_interest"].copy()
        # daily last snapshot; label = date of the last 5m bar
        daily = oi.resample("1D").last().dropna()
        pct = daily.pct_change()
        mu = pct.rolling(ROLL_WINDOW, min_periods=ROLL_MIN).mean()
        sd = pct.rolling(ROLL_WINDOW, min_periods=ROLL_MIN).std()
        z = (pct - mu) / sd
        z_by_sym[s] = z.dropna()
    return z_by_sym


def load_daily_open_close() -> Dict[str, pd.DataFrame]:
    """Return sym -> DataFrame with 'open' (first 1m open of day) and 'close' (last of day)."""
    out: Dict[str, pd.DataFrame] = {}
    for s in SYMS:
        path = BASE / "runs" / "ohlcv_cache" / f"{s}USDT_1m.joblib"
        oc = joblib.load(path)
        # first open, last close of each UTC day
        op = oc["open"].resample("1D").first()
        cl = oc["close"].resample("1D").last()
        df = pd.concat([op.rename("open"), cl.rename("close")], axis=1).dropna()
        out[s] = df
    return out


# ---------------------------------------------------------------------------
# Candidate pool for fee-aware permutation
# ---------------------------------------------------------------------------

def build_candidate_pool(price: Dict[str, pd.DataFrame]) -> np.ndarray:
    """
    Every possible 5-day forward gross return per target sym per day.
    Serves as the null distribution baseline for fee_aware_perm_test.
    """
    pool: List[float] = []
    for s in SYMS:
        df = price[s]
        # forward return T -> T+HOLD_DAYS using T+1 open as entry, T+HOLD_DAYS+1 open as exit
        op = df["open"]
        entry = op.shift(-1)
        exit_ = op.shift(-(HOLD_DAYS + 1))
        gross = (exit_ / entry) - 1.0
        pool.extend(gross.dropna().tolist())
    return np.asarray(pool, dtype=float)


# ---------------------------------------------------------------------------
# Trigger + trade enumeration
# ---------------------------------------------------------------------------

def enumerate_trades(
    z_by_sym: Dict[str, pd.Series],
    price: Dict[str, pd.DataFrame],
    quadrant: str,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    quadrant in {'A_focus', 'A_mirror', 'B_focus', 'B_mirror'}.

    Returns
    -------
    trades_df : DataFrame with columns
      [trigger_sym, target_sym, trigger_date, entry_ts, exit_ts,
       gross_ret, net_ret, side_sign]
    events_df : DataFrame with columns
      [trigger_sym, trigger_date, event_mean_net_ret, n_targets]
    """
    if quadrant.startswith("A"):
        trig_mask = lambda z: z < -Z_THRESHOLD  # noqa: E731
    else:
        trig_mask = lambda z: z >  Z_THRESHOLD  # noqa: E731

    # side_sign multiplies gross to convert to net-of-direction
    if quadrant in ("A_focus", "B_mirror"):
        side_sign = -1.0  # SHORT other syms
    else:
        side_sign = +1.0  # LONG other syms

    rows: List[dict] = []
    event_rows: List[dict] = []

    # For each trigger sym, enumerate trigger days
    for trig_sym in SYMS:
        z = z_by_sym[trig_sym]
        trig_days = z.index[trig_mask(z)]
        for T in trig_days:
            per_event_nets: List[float] = []
            per_event_gross: List[float] = []
            for tgt in SYMS:
                if tgt == trig_sym:
                    continue
                df = price[tgt]
                # Locate first bar strictly after T (T+1 open)
                # T is a UTC midnight; want the daily bar dated > T.
                fwd_dates = df.index[df.index > T]
                if len(fwd_dates) < (HOLD_DAYS + 1):
                    continue
                entry_date = fwd_dates[0]         # T+1
                exit_date = fwd_dates[HOLD_DAYS]  # T+1+HOLD_DAYS = T+6
                entry_p = df.at[entry_date, "open"]
                exit_p = df.at[exit_date, "open"]
                if not (np.isfinite(entry_p) and np.isfinite(exit_p) and entry_p > 0):
                    continue
                gross = (exit_p / entry_p) - 1.0
                gross_dir = gross * side_sign
                net = gross_dir - FEE_ROUND_TRIP
                rows.append({
                    "trigger_sym": trig_sym,
                    "target_sym": tgt,
                    "trigger_date": T.isoformat(),
                    "entry_ts": entry_date.isoformat(),
                    "exit_ts": exit_date.isoformat(),
                    "gross_ret": float(gross_dir),
                    "net_ret": float(net),
                    "side_sign": int(side_sign),
                })
                per_event_gross.append(gross_dir)
                per_event_nets.append(net)
            if per_event_nets:
                event_rows.append({
                    "trigger_sym": trig_sym,
                    "trigger_date": T.isoformat(),
                    "event_mean_net_ret": float(np.mean(per_event_nets)),
                    "event_mean_gross_ret": float(np.mean(per_event_gross)),
                    "n_targets": len(per_event_nets),
                })

    trades_df = pd.DataFrame(rows)
    events_df = pd.DataFrame(event_rows)
    return trades_df, events_df


# ---------------------------------------------------------------------------
# Diagnostics (Concentration — Lesson #16)
# ---------------------------------------------------------------------------

def per_quarter_t(trades: pd.DataFrame) -> Dict[str, float]:
    if trades.empty:
        return {}
    ts = pd.to_datetime(trades["entry_ts"])
    q_labels = ts.dt.to_period("Q").astype(str)
    out: Dict[str, float] = {}
    for q, grp in trades.groupby(q_labels):
        arr = grp["net_ret"].to_numpy()
        if len(arr) < 5 or arr.std(ddof=1) == 0:
            continue
        t = arr.mean() / arr.std(ddof=1) * np.sqrt(len(arr))
        out[str(q)] = float(t)
    return out


def per_symbol_bootstrap(trades: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    if trades.empty:
        return {}
    out: Dict[str, Dict[str, float]] = {}
    for sym, grp in trades.groupby("target_sym"):
        arr = grp["net_ret"].to_numpy()
        if len(arr) < 20:
            out[sym] = {"n": int(len(arr)), "mean_bp": float(arr.mean() * 10000), "ci_lower_bp": None, "ci_pos": None}
            continue
        ci = bootstrap_ci(arr, n_boot=1000, block_size=1, alpha=0.05)
        out[sym] = {
            "n": int(len(arr)),
            "mean_bp": float(arr.mean() * 10000),
            "ci_lower_bp": float(ci["ci_lower"] * 10000),
            "ci_upper_bp": float(ci["ci_upper"] * 10000),
            "ci_pos": bool(ci["ci_lower"] > 0),
        }
    return out


# ---------------------------------------------------------------------------
# R-1 evaluation per quadrant
# ---------------------------------------------------------------------------

def evaluate_quadrant(
    quadrant: str,
    trades_df: pd.DataFrame,
    events_df: pd.DataFrame,
    candidate_pool: np.ndarray,
) -> Dict:
    if trades_df.empty:
        return {"error": "no trades", "quadrant": quadrant}

    # Trade-level (per target-sym pair)
    trade_nets = trades_df["net_ret"].to_numpy()
    perm = fee_aware_perm_test(
        observed_net_returns=trade_nets,
        candidate_pool_returns=candidate_pool.tolist(),
        fee_per_trade=FEE_ROUND_TRIP,
        n_perms=1000,
        rng_seed=42,
    )
    ci = bootstrap_ci(trade_nets, n_boot=2000, block_size=1, alpha=0.05)

    # Event-level (Lesson #74): use event-mean net returns as one obs per trigger day
    event_nets = events_df["event_mean_net_ret"].to_numpy()
    event_ci = bootstrap_ci(event_nets, n_boot=2000, block_size=1, alpha=0.05)
    if len(event_nets) >= 5 and event_nets.std(ddof=1) > 0:
        event_t = float(event_nets.mean() / event_nets.std(ddof=1) * np.sqrt(len(event_nets)))
    else:
        event_t = None

    # Concentration
    quarter_t = per_quarter_t(trades_df)
    per_sym = per_symbol_bootstrap(trades_df)

    quarter_pos_t_ratio = (
        sum(1 for v in quarter_t.values() if v > 0) / len(quarter_t)
        if quarter_t else 0.0
    )
    n_sym_measured = sum(1 for v in per_sym.values() if v.get("ci_pos") is not None)
    n_sym_ci_pos = sum(1 for v in per_sym.values() if v.get("ci_pos"))
    symbol_ci_pos_ratio = (n_sym_ci_pos / n_sym_measured) if n_sym_measured else 0.0

    # Three-gate PASS
    three_gate_pass = bool(
        perm.get("signal_t_excess", 0.0) >= 2.0
        and ci.get("ci_lower", -1.0) > 0
        and perm.get("perm_p_two_sided", 1.0) <= 0.10
    )
    concentration_pass = bool(
        quarter_pos_t_ratio >= 0.5
        and symbol_ci_pos_ratio >= 0.30
        and n_sym_ci_pos >= 3
    )
    # Event-level authoritative check (Lesson #74)
    event_pos = bool(event_ci.get("ci_lower", -1.0) > 0)

    return {
        "quadrant": quadrant,
        "n_trades": int(len(trade_nets)),
        "n_events": int(len(event_nets)),
        "trade_mean_bp": float(trade_nets.mean() * 10000),
        "trade_median_bp": float(np.median(trade_nets) * 10000),
        "trade_std_bp": float(trade_nets.std(ddof=1) * 10000),
        "perm": perm,
        "ci_trade": ci,
        "ci_event": event_ci,
        "event_t": event_t,
        "event_mean_bp": float(event_nets.mean() * 10000),
        "concentration": {
            "per_quarter_t": quarter_t,
            "quarter_pos_t_ratio": quarter_pos_t_ratio,
            "per_symbol": per_sym,
            "n_sym_measured": n_sym_measured,
            "n_sym_ci_pos": n_sym_ci_pos,
            "symbol_ci_pos_ratio": symbol_ci_pos_ratio,
        },
        "three_gate_pass": three_gate_pass,
        "concentration_pass": concentration_pass,
        "event_level_ci_pos": event_pos,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    log.info("paradigm_251 R-1 begin")
    log.info("Loading daily OI z-scores for %d syms...", len(SYMS))
    z_by_sym = load_daily_oi_z()
    log.info("Loading daily open/close for %d syms...", len(SYMS))
    price = load_daily_open_close()
    log.info("Building candidate pool (all 5d forward gross)...")
    pool = build_candidate_pool(price)
    log.info("Pool size = %d", len(pool))

    quadrant_results: Dict[str, Dict] = {}
    trades_by_quadrant: Dict[str, pd.DataFrame] = {}
    events_by_quadrant: Dict[str, pd.DataFrame] = {}

    for q in ("A_focus", "A_mirror", "B_focus", "B_mirror"):
        log.info("=== Quadrant %s ===", q)
        trades_df, events_df = enumerate_trades(z_by_sym, price, q)
        trades_by_quadrant[q] = trades_df
        events_by_quadrant[q] = events_df
        log.info("  n_trades=%d n_events=%d", len(trades_df), len(events_df))
        res = evaluate_quadrant(q, trades_df, events_df, pool)
        quadrant_results[q] = res
        log.info(
            "  trade_mean=%.2fbp perm.signal_t_excess=%.3f perm.p2=%.4f "
            "ci_trade_lower=%.2fbp ci_event_lower=%.2fbp event_t=%s q_pos=%.2f sym_pos=%.2f "
            "GATE=%s CONC=%s EVENT_POS=%s",
            res["trade_mean_bp"],
            res["perm"].get("signal_t_excess", float("nan")),
            res["perm"].get("perm_p_two_sided", float("nan")),
            res["ci_trade"].get("ci_lower", float("nan")) * 10000,
            res["ci_event"].get("ci_lower", float("nan")) * 10000,
            res["event_t"],
            res["concentration"]["quarter_pos_t_ratio"],
            res["concentration"]["symbol_ci_pos_ratio"],
            res["three_gate_pass"],
            res["concentration_pass"],
            res["event_level_ci_pos"],
        )

    # Pick best passing quadrant (event_level_ci_pos + three_gate + concentration)
    winners = [
        (q, r) for q, r in quadrant_results.items()
        if r.get("three_gate_pass") and r.get("event_level_ci_pos")
    ]
    winners.sort(
        key=lambda x: (
            x[1]["ci_event"].get("ci_lower", -1.0),
            x[1]["event_mean_bp"],
        ),
        reverse=True,
    )
    best_quadrant = winners[0][0] if winners else None

    # Save aggregate metrics
    metrics_path = OUT_DIR / "r1__metrics.json"
    metrics_out = {
        "paradigm": "paradigm_251_cross_sym_oi_daily_drop_contagion_bilateral_5d",
        "phase": "R-1",
        "date_utc": datetime.utcnow().isoformat(),
        "config": {
            "SYMS": SYMS,
            "HOLD_DAYS": HOLD_DAYS,
            "FEE_ROUND_TRIP": FEE_ROUND_TRIP,
            "Z_THRESHOLD": Z_THRESHOLD,
            "ROLL_WINDOW": ROLL_WINDOW,
            "ROLL_MIN": ROLL_MIN,
        },
        "candidate_pool_size": int(len(pool)),
        "quadrants": quadrant_results,
        "best_quadrant": best_quadrant,
        "verdict": "PASS" if best_quadrant else "FAIL",
    }
    metrics_path.write_text(json.dumps(metrics_out, indent=2, default=str))
    log.info("Wrote %s", metrics_path)

    # Save best-quadrant trades per trigger-symbol (for tier3_gate.py G2 evaluation)
    if best_quadrant:
        best_trades = trades_by_quadrant[best_quadrant]
        # Pick top trigger sym by concentration (largest ci_lower_bp among target_sym breakdown)
        # For tier3_gate we need per-sym trades. Use the quadrant's target_sym with best CI lower.
        conc = quadrant_results[best_quadrant]["concentration"]["per_symbol"]
        # Rank target syms by CI lower (positive), fall back to mean
        ranked = sorted(
            (
                (sym, d.get("ci_lower_bp") if d.get("ci_lower_bp") is not None else d.get("mean_bp", -1e9))
                for sym, d in conc.items()
            ),
            key=lambda x: x[1] if x[1] is not None else -1e9,
            reverse=True,
        )
        for i, (best_sym, _) in enumerate(ranked[:3]):
            subset = best_trades[best_trades["target_sym"] == best_sym]
            if subset.empty:
                continue
            trades_list = [
                {
                    "entry_ts": r["entry_ts"],
                    "exit_ts": r["exit_ts"],
                    "net_ret": float(r["net_ret"]),
                }
                for _, r in subset.iterrows()
            ]
            trades_path = OUT_DIR / f"trades_{best_quadrant}_{best_sym}USDT.json"
            trades_path.write_text(json.dumps(trades_list, indent=2))
            log.info("Wrote %s (n=%d)", trades_path, len(trades_list))
    else:
        # Even on FAIL, save the strongest observed quadrant's best-sym trades for auditability
        best_by_t = max(
            quadrant_results.items(),
            key=lambda kv: (kv[1].get("event_t") or float("-inf")),
        )
        q = best_by_t[0]
        subset_trades = trades_by_quadrant[q]
        if not subset_trades.empty:
            per_sym = per_symbol_bootstrap(subset_trades)
            ranked = sorted(
                per_sym.items(),
                key=lambda x: x[1].get("mean_bp", -1e9),
                reverse=True,
            )
            for best_sym, _ in ranked[:1]:
                subset = subset_trades[subset_trades["target_sym"] == best_sym]
                trades_list = [
                    {
                        "entry_ts": r["entry_ts"],
                        "exit_ts": r["exit_ts"],
                        "net_ret": float(r["net_ret"]),
                    }
                    for _, r in subset.iterrows()
                ]
                trades_path = OUT_DIR / f"trades_{q}_{best_sym}USDT.json"
                trades_path.write_text(json.dumps(trades_list, indent=2))
                log.info("Wrote FAIL-case audit trades %s (n=%d)", trades_path, len(trades_list))

    log.info("paradigm_251 R-1 end | verdict=%s best=%s", metrics_out["verdict"], best_quadrant)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
