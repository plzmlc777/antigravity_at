"""R-2 — btc_rv_spike_highvol_filter_alt_long_240m.

Purpose
-------
Promote R-1 PoC to R-2 with the formal Research Track elite gate evaluation:

Step A — Vol cutoff finalization (p75 vs p80 vs p85 vs p90)
Step B — Full coarse param grid: hold × SL × TP (6 × 4 × 4 = 96 cells)
         at the cutoff chosen in Step A.
Step C — Quarterly fold at best cell (decisive 2026Q1 regime check)
Step D — Per-symbol breakdown at best cell (13 alts)
Step E — Capacity check (trades/year, average concurrent positions)
Step F — Final robust stats at best cell (perm n=1000, bootstrap n=2000)
Step G — Comparison to R-1 baseline

Output
------
backend/runs/research_track/btc_rv_spike_highvol_filter_alt_long_240m/r2__metrics.json

R-1 PASS confirmed (n=689 +42.78bp t=+3.16 signal_t_excess=+4.73 perm_p=0.000).
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from scripts.research._perm_utils import (  # noqa: E402
    bootstrap_ci,
    fee_aware_perm_test,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("btc_rv_highvol_r2")

PARADIGM = "btc_rv_spike_highvol_filter_alt_long_240m"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM
OUT_PATH = OUT_DIR / "r2__metrics.json"

BTC = "BTCUSDT"
ALTS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT", "ETHUSDT",
    "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

# Identical signal config (do NOT touch these — R-1 PASSed with these)
RV_WINDOW = 30
Z_WINDOW = 30 * 24 * 60
Z_THRESH = 2.5
COOLDOWN = 60
FEE_RT = 8e-4

# Step A — vol cutoff grid
STEP_A_CUTOFFS = [0.75, 0.80, 0.85, 0.90]
STEP_A_HOLD = 240

# Step B — full coarse grid
HOLDS_GRID = [180, 210, 240, 270, 300, 360]
SLS_GRID = [None, 0.03, 0.05, 0.08]  # decimals
TPS_GRID = [None, 0.05, 0.08, 0.10]

# Vol regime config (identical to R-1)
VOL_LOOKBACK_BARS = 30 * 24 * 60
VOL_DIST_BARS = 90 * 24 * 60
VOL_MIN_PERIODS = 90 * 24 * 60

# Per-cell light perm/boot for grid (Step B). Best cell gets heavy n later.
GRID_N_PERMS = 200
GRID_N_BOOT = 400

# Final stats (Step F)
FINAL_N_PERMS = 1000
FINAL_N_BOOT = 2000
N_POOL_SAMPLES = 20000

SEED = 42

# Approx total alt-bars per sym (547200) × 13 alts ≈ 7.1M bars.
# Trigger-driven evaluation is cheap: at p75 cutoff trigger count ~53.


# ---------- data ----------


def load_ohlcv_1m(db, sym: str) -> pd.DataFrame:
    rows = db.execute(
        text(
            "SELECT timestamp, open, high, low, close FROM ohlcv "
            "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
        ),
        {"s": sym},
    ).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    for c in ("open", "high", "low", "close"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[~df.index.duplicated(keep="first")]
    return df


def compute_btc_signal(btc: pd.DataFrame) -> pd.DataFrame:
    lr = np.log(btc["close"]).diff()
    rv = lr.rolling(RV_WINDOW, min_periods=RV_WINDOW).std()
    rv_mu = rv.rolling(Z_WINDOW, min_periods=Z_WINDOW).mean()
    rv_sd = rv.rolling(Z_WINDOW, min_periods=Z_WINDOW).std()
    rv_z = (rv - rv_mu) / rv_sd
    btc_ret_30m = btc["close"] / btc["close"].shift(RV_WINDOW) - 1
    sig = pd.DataFrame({"rv": rv, "rv_z": rv_z, "btc_ret_30m": btc_ret_30m}).dropna()
    return sig


def extract_triggers(sig: pd.DataFrame, z_thresh: float = Z_THRESH) -> pd.DataFrame:
    z_prev = sig["rv_z"].shift(1)
    fire = (sig["rv_z"] > z_thresh) & (z_prev <= z_thresh)
    triggers = sig[fire].copy()
    triggers = triggers[triggers["btc_ret_30m"] > 0]
    if len(triggers) == 0:
        return triggers
    keep = [True]
    last_t = triggers.index[0]
    for ts in triggers.index[1:]:
        delta_min = (ts - last_t).total_seconds() / 60.0
        if delta_min < COOLDOWN:
            keep.append(False)
        else:
            keep.append(True)
            last_t = ts
    return triggers[keep]


def compute_btc_vol_regime(btc: pd.DataFrame, cutoffs) -> pd.DataFrame:
    close = btc["close"]
    lr = np.log(close).diff()
    rv_30d = lr.rolling(VOL_LOOKBACK_BARS, min_periods=VOL_LOOKBACK_BARS).std() * np.sqrt(60 * 24)
    cols = {"rv_30d": rv_30d}
    for c in cutoffs:
        cols[f"p{int(c*100)}"] = rv_30d.rolling(VOL_DIST_BARS, min_periods=VOL_MIN_PERIODS).quantile(c)
    return pd.DataFrame(cols)


def filter_triggers_by_vol_cutoff(triggers: pd.DataFrame, vol_df: pd.DataFrame, cutoff: float) -> pd.DataFrame:
    col = f"p{int(cutoff*100)}"
    if col not in vol_df.columns:
        return triggers.iloc[0:0]
    keep_mask = []
    for ts in triggers.index:
        if ts not in vol_df.index:
            keep_mask.append(False)
            continue
        rv = vol_df.at[ts, "rv_30d"]
        thr = vol_df.at[ts, col]
        if pd.isna(rv) or pd.isna(thr):
            keep_mask.append(False)
        else:
            keep_mask.append(bool(rv > thr))
    return triggers[keep_mask]


# ---------- trade simulation ----------


def simulate_trade(high_arr, low_arr, close_arr, ts_to_pos, trig_ts, hold_min, sl, tp):
    entry_ts = trig_ts + pd.Timedelta(minutes=1)
    final_exit_ts = trig_ts + pd.Timedelta(minutes=1 + hold_min)
    ei = ts_to_pos.get(entry_ts)
    xi = ts_to_pos.get(final_exit_ts)
    if ei is None or xi is None:
        return float("nan"), "invalid"
    entry_p = close_arr[ei]
    if not (entry_p > 0) or np.isnan(entry_p):
        return float("nan"), "invalid"
    bar_lows = low_arr[ei + 1: xi + 1]
    bar_highs = high_arr[ei + 1: xi + 1]
    bar_closes = close_arr[ei + 1: xi + 1]
    if len(bar_closes) == 0:
        return float("nan"), "invalid"
    sl_price = entry_p * (1.0 - sl) if sl else None
    tp_price = entry_p * (1.0 + tp) if tp else None
    exit_reason = "time"
    exit_price = bar_closes[-1]
    for k in range(len(bar_closes)):
        lo = bar_lows[k]
        hi = bar_highs[k]
        sl_hit = sl_price is not None and not np.isnan(lo) and lo <= sl_price
        tp_hit = tp_price is not None and not np.isnan(hi) and hi >= tp_price
        if sl_hit:
            exit_price = sl_price
            exit_reason = "sl"
            break
        if tp_hit:
            exit_price = tp_price
            exit_reason = "tp"
            break
    gross = exit_price / entry_p - 1.0
    return float(gross), exit_reason


def run_cell(alt_data, alt_lookup, triggers, hold, sl, tp):
    """Run trigger panel into per-trade net returns."""
    nets, sym_list, ts_list, reasons = [], [], [], []
    trig_idx = list(triggers.index)
    for sym, df_dict in alt_data.items():
        ha = df_dict["high"]
        la = df_dict["low"]
        ca = df_dict["close"]
        ts_pos = alt_lookup[sym]
        for trig_ts in trig_idx:
            gross, reason = simulate_trade(ha, la, ca, ts_pos, trig_ts, hold, sl, tp)
            if np.isnan(gross):
                continue
            net = gross - FEE_RT
            nets.append(net)
            sym_list.append(sym)
            ts_list.append(trig_ts)
            reasons.append(reason)
    nets_arr = np.array(nets, dtype=float)
    if len(nets_arr) < 2:
        return {
            "hold": hold, "sl": sl, "tp": tp,
            "n_trades": 0, "net_mean_bp": float("nan"),
            "t": float("nan"), "win": float("nan"), "sharpe": float("nan"),
            "nets": [], "sym": [], "ts": [], "reasons": [],
        }
    n = len(nets_arr)
    mn = float(nets_arr.mean())
    sd = float(nets_arr.std(ddof=1))
    t_stat = mn / sd * np.sqrt(n) if sd > 0 else 0.0
    return {
        "hold": hold, "sl": sl, "tp": tp,
        "n_trades": n,
        "net_mean_bp": mn * 1e4,
        "t": t_stat,
        "win": float((nets_arr > 0).mean()),
        "sharpe": (mn / sd) if sd > 0 else 0.0,
        "nets": nets_arr.tolist(),
        "sym": sym_list,
        "ts": [str(x) for x in ts_list],
        "reasons": reasons,
    }


def build_candidate_pool(alt_data, alt_lookup, hold, sl, tp, n_samples=N_POOL_SAMPLES, seed=SEED):
    rng = np.random.default_rng(seed)
    pool = []
    sym_keys = list(alt_data.keys())
    n_per_sym = n_samples // max(len(sym_keys), 1)
    for sym in sym_keys:
        ha = alt_data[sym]["high"]
        la = alt_data[sym]["low"]
        ca = alt_data[sym]["close"]
        ts_pos = alt_lookup[sym]
        ts_list = list(ts_pos.keys())
        max_i = len(ts_list) - hold - 5
        if max_i <= 0:
            continue
        idxs = rng.choice(max_i, size=min(n_per_sym, max_i), replace=False)
        for idx in idxs:
            trig_ts = ts_list[idx]
            gross, _ = simulate_trade(ha, la, ca, ts_pos, trig_ts, hold, sl, tp)
            if not np.isnan(gross):
                pool.append(gross)
    return np.array(pool, dtype=float)


def stats_block(nets_arr: np.ndarray) -> dict:
    if len(nets_arr) < 2:
        return {"n": int(len(nets_arr)), "mean_bp": float("nan"), "t": float("nan"), "win": float("nan")}
    m = float(nets_arr.mean())
    s = float(nets_arr.std(ddof=1))
    t_s = m / s * np.sqrt(len(nets_arr)) if s > 0 else 0.0
    return {
        "n": int(len(nets_arr)),
        "mean_bp": m * 1e4,
        "t": t_s,
        "win": float((nets_arr > 0).mean()),
        "sharpe": (m / s) if s > 0 else 0.0,
    }


def quarterly_stats(nets_arr: np.ndarray, ts_arr: pd.DatetimeIndex) -> list:
    quarter_edges = [
        ("2025Q3", pd.Timestamp("2025-07-01"), pd.Timestamp("2025-10-01")),
        ("2025Q4", pd.Timestamp("2025-10-01"), pd.Timestamp("2026-01-01")),
        ("2026Q1", pd.Timestamp("2026-01-01"), pd.Timestamp("2026-04-01")),
        ("2026Q2", pd.Timestamp("2026-04-01"), pd.Timestamp("2026-07-01")),
    ]
    out = []
    for qname, qstart, qend in quarter_edges:
        mask = (ts_arr >= qstart) & (ts_arr < qend)
        sub = nets_arr[mask.values] if hasattr(mask, "values") else nets_arr[mask]
        if len(sub) < 5:
            out.append({"quarter": qname, "n": int(len(sub)), "note": "insufficient"})
            continue
        out.append({"quarter": qname, **stats_block(sub)})
    return out


# ---------- main ----------


def main():
    t_start = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "paradigm": PARADIGM,
        "phase": "R-2",
        "hypothesis": (
            "BTC 30m RV z>=2.5 rising + up-trigger + 60m cooldown + 30d RV > pXX(90d) -> "
            "LONG 13 alts, hold=H min, SL/TP grid"
        ),
        "config": {
            "rv_window_bars": RV_WINDOW,
            "z_window_bars": Z_WINDOW,
            "z_thresh": Z_THRESH,
            "cooldown_min": COOLDOWN,
            "fee_round_trip": FEE_RT,
            "step_a_cutoffs": STEP_A_CUTOFFS,
            "step_a_hold": STEP_A_HOLD,
            "holds_grid": HOLDS_GRID,
            "sls_grid": SLS_GRID,
            "tps_grid": TPS_GRID,
            "vol_lookback_bars": VOL_LOOKBACK_BARS,
            "vol_dist_bars": VOL_DIST_BARS,
            "vol_min_periods": VOL_MIN_PERIODS,
            "grid_n_perms": GRID_N_PERMS,
            "grid_n_boot": GRID_N_BOOT,
            "final_n_perms": FINAL_N_PERMS,
            "final_n_boot": FINAL_N_BOOT,
            "n_pool_samples": N_POOL_SAMPLES,
            "alts": ALTS,
            "data_source": "Mint DB ohlcv 1m",
            "expected_btc_bars": 547200,
        },
        "r1_baseline": {
            "n_trades": 689,
            "net_mean_bp": 42.78,
            "t": 3.16,
            "signal_t_excess": 4.73,
            "ci_lower_bp": 16.10,
            "ci_upper_bp": 70.25,
            "perm_p_above": 0.000,
            "unfiltered_baseline_n_trades": 2626,
            "unfiltered_baseline_mean_bp": 14.36,
        },
    }

    db = SessionLocal()
    try:
        log.info("Loading BTC ohlcv 1m ...")
        btc = load_ohlcv_1m(db, BTC)
        if btc.empty:
            raise SystemExit("BTC ohlcv empty")
        log.info("BTC bars=%d range=%s..%s", len(btc), btc.index[0], btc.index[-1])
        out["data_window"] = {
            "btc_first": str(btc.index[0]),
            "btc_last": str(btc.index[-1]),
            "btc_bars": int(len(btc)),
        }
        if len(btc) != 547200:
            out["verdict"] = "FAIL"
            out["verdict_reasons_fail"] = [f"btc bars {len(btc)} != 547200, wrong DB"]
            OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
            return

        log.info("Computing BTC RV signal ...")
        sig = compute_btc_signal(btc)
        log.info("Computing BTC vol regime ...")
        all_cutoffs = sorted(set(STEP_A_CUTOFFS + [0.75]))
        vol_df = compute_btc_vol_regime(btc, all_cutoffs)

        triggers_unfilt = extract_triggers(sig, z_thresh=Z_THRESH)
        log.info("Unfiltered triggers: %d", len(triggers_unfilt))
        out["n_triggers_unfiltered"] = int(len(triggers_unfilt))

        log.info("Loading %d alts ...", len(ALTS))
        alt_data = {}
        alt_lookup = {}
        for sym in ALTS:
            df = load_ohlcv_1m(db, sym)
            if df.empty:
                log.warning("alt %s empty", sym)
                continue
            alt_data[sym] = {
                "high": df["high"].values,
                "low": df["low"].values,
                "close": df["close"].values,
                "index": df.index,
            }
            alt_lookup[sym] = {ts: i for i, ts in enumerate(df.index)}
        log.info("loaded %d alts", len(alt_data))
        out["alts_loaded"] = len(alt_data)

        # ============================================================
        # Build candidate pool ONCE for hold=240 (re-used for grid cells
        # with hold=240; cells with different hold use their own pool).
        # ============================================================
        log.info("Building global candidate pool (hold=%d, n=%d) ...", STEP_A_HOLD, N_POOL_SAMPLES)
        pool_240 = build_candidate_pool(alt_data, alt_lookup, STEP_A_HOLD, None, None,
                                        n_samples=N_POOL_SAMPLES, seed=SEED)
        log.info("pool_240 size=%d", len(pool_240))

        # ============================================================
        # STEP A — vol cutoff finalization (p75 vs p80 vs p85 vs p90)
        # ============================================================
        log.info("=== STEP A: vol cutoff finalization ===")
        step_a_results = []
        for cutoff in STEP_A_CUTOFFS:
            trig_filt = filter_triggers_by_vol_cutoff(triggers_unfilt, vol_df, cutoff)
            if len(trig_filt) < 10:
                step_a_results.append({
                    "cutoff_pct": int(cutoff * 100),
                    "n_triggers": int(len(trig_filt)),
                    "note": "insufficient triggers",
                })
                continue
            cell = run_cell(alt_data, alt_lookup, trig_filt, STEP_A_HOLD, None, None)
            if cell["n_trades"] < 30:
                step_a_results.append({
                    "cutoff_pct": int(cutoff * 100),
                    "n_triggers": int(len(trig_filt)),
                    "n_trades": cell["n_trades"],
                    "note": "insufficient trades",
                })
                continue
            nets = np.array(cell["nets"])
            ts_arr = pd.DatetimeIndex(pd.to_datetime(cell["ts"]))
            fe = fee_aware_perm_test(nets, pool_240, fee_per_trade=FEE_RT,
                                     n_perms=GRID_N_PERMS, rng_seed=SEED)
            bs = bootstrap_ci(nets, n_boot=GRID_N_BOOT, block_size=1, rng_seed=SEED)
            qrt = quarterly_stats(nets, ts_arr)
            row = {
                "cutoff_pct": int(cutoff * 100),
                "n_triggers": int(len(trig_filt)),
                "n_trades": cell["n_trades"],
                "net_mean_bp": cell["net_mean_bp"],
                "t": cell["t"],
                "win": cell["win"],
                "sharpe": cell["sharpe"],
                "signal_t_excess": fe["signal_t_excess"],
                "ci_lower_bp": bs["ci_lower"] * 1e4,
                "ci_upper_bp": bs["ci_upper"] * 1e4,
                "perm_p_above": fe["perm_p_one_sided_above"],
                "quarterly": qrt,
            }
            step_a_results.append(row)
            log.info("  p%d: n=%d mean=%+.2fbp t=%+.2f sig_t_ex=%+.2f ci_lo=%+.2f perm_p_above=%.4f",
                     int(cutoff * 100), cell["n_trades"], cell["net_mean_bp"],
                     cell["t"], fe["signal_t_excess"], bs["ci_lower"] * 1e4,
                     fe["perm_p_one_sided_above"])
        out["step_a_cutoff_finalization"] = step_a_results

        # Decision rule: best cutoff balances capacity AND alpha strength.
        # Require trades/yr >= 100 (assume data ~1y), so n_trades >= 100.
        # Among those, pick the one with highest signal_t_excess.
        candidates = [r for r in step_a_results if r.get("n_trades", 0) >= 100]
        if not candidates:
            # Fall back to any cell with sufficient trades.
            candidates = [r for r in step_a_results if r.get("n_trades", 0) >= 30]
        if not candidates:
            out["verdict"] = "GRAVEYARD"
            out["verdict_reasons_fail"] = ["Step A: no cutoff has >=30 trades"]
            out["wall_clock_min"] = round((time.time() - t_start) / 60, 2)
            OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
            return
        best_cutoff_row = max(candidates, key=lambda r: r.get("signal_t_excess", -99))
        best_cutoff_pct = best_cutoff_row["cutoff_pct"]
        best_cutoff = best_cutoff_pct / 100.0
        out["step_a_best_cutoff_pct"] = best_cutoff_pct
        log.info("Step A best cutoff: p%d (n=%d sig_t_ex=%+.2f)",
                 best_cutoff_pct, best_cutoff_row["n_trades"],
                 best_cutoff_row["signal_t_excess"])

        # ============================================================
        # STEP B — full parameter grid (coarse) at best cutoff
        # ============================================================
        log.info("=== STEP B: full grid (%d×%d×%d=%d cells) at p%d ===",
                 len(HOLDS_GRID), len(SLS_GRID), len(TPS_GRID),
                 len(HOLDS_GRID) * len(SLS_GRID) * len(TPS_GRID), best_cutoff_pct)
        triggers_best = filter_triggers_by_vol_cutoff(triggers_unfilt, vol_df, best_cutoff)
        out["step_b_n_triggers"] = int(len(triggers_best))

        # Pre-compute pools per hold (reused across SL/TP variants)
        pool_by_hold = {STEP_A_HOLD: pool_240}
        for h in HOLDS_GRID:
            if h not in pool_by_hold:
                log.info("Building pool for hold=%d ...", h)
                pool_by_hold[h] = build_candidate_pool(
                    alt_data, alt_lookup, h, None, None,
                    n_samples=N_POOL_SAMPLES, seed=SEED)

        grid_results = []
        elapsed_check_every = 10
        n_cells = 0
        t_grid_start = time.time()
        for hold in HOLDS_GRID:
            for sl in SLS_GRID:
                for tp in TPS_GRID:
                    n_cells += 1
                    # Build trades
                    cell = run_cell(alt_data, alt_lookup, triggers_best, hold, sl, tp)
                    if cell["n_trades"] < 30:
                        grid_results.append({
                            "hold": hold, "sl": sl, "tp": tp,
                            "n_trades": cell["n_trades"],
                            "note": "insufficient",
                        })
                        continue
                    nets = np.array(cell["nets"])
                    pool_h = pool_by_hold[hold]
                    fe = fee_aware_perm_test(nets, pool_h, fee_per_trade=FEE_RT,
                                             n_perms=GRID_N_PERMS, rng_seed=SEED)
                    bs = bootstrap_ci(nets, n_boot=GRID_N_BOOT, block_size=1, rng_seed=SEED)
                    row = {
                        "hold": hold, "sl": sl, "tp": tp,
                        "n_trades": cell["n_trades"],
                        "net_mean_bp": cell["net_mean_bp"],
                        "t": cell["t"],
                        "win": cell["win"],
                        "sharpe": cell["sharpe"],
                        "signal_t_excess": fe["signal_t_excess"],
                        "ci_lower_bp": bs["ci_lower"] * 1e4,
                        "ci_upper_bp": bs["ci_upper"] * 1e4,
                        "perm_p_above": fe["perm_p_one_sided_above"],
                    }
                    grid_results.append(row)
                    if n_cells % elapsed_check_every == 0:
                        elapsed = time.time() - t_grid_start
                        log.info("  grid progress %d/%d cells (%.1fs)", n_cells,
                                 len(HOLDS_GRID) * len(SLS_GRID) * len(TPS_GRID), elapsed)
        out["step_b_grid"] = grid_results

        # Plateau count — 4-gate strict
        plateau_cells = [
            r for r in grid_results
            if r.get("t", -99) >= 2.5
            and r.get("signal_t_excess", -99) >= 2.5
            and r.get("ci_lower_bp", -99) > 0
            and r.get("perm_p_above", 1) <= 0.05
        ]
        out["step_b_plateau_count"] = len(plateau_cells)
        log.info("Plateau (4-gate strict): %d / %d cells", len(plateau_cells), len(grid_results))

        # Top 5 cells by signal_t_excess
        ranked = sorted([r for r in grid_results if "signal_t_excess" in r],
                        key=lambda r: r.get("signal_t_excess", -99), reverse=True)
        top5 = ranked[:5]
        out["step_b_top5"] = top5
        log.info("Top-5 by signal_t_excess:")
        for r in top5:
            log.info("  hold=%d sl=%s tp=%s: n=%d mean=%+.2fbp t=%+.2f sig_t_ex=%+.2f ci_lo=%+.2f",
                     r["hold"], r["sl"], r["tp"], r["n_trades"], r["net_mean_bp"],
                     r["t"], r["signal_t_excess"], r["ci_lower_bp"])

        if not ranked:
            out["verdict"] = "GRAVEYARD"
            out["verdict_reasons_fail"] = ["Step B: no valid cells"]
            out["wall_clock_min"] = round((time.time() - t_start) / 60, 2)
            OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
            return

        best_cell = ranked[0]
        out["best_cell"] = {
            "hold": best_cell["hold"],
            "sl": best_cell["sl"],
            "tp": best_cell["tp"],
            "cutoff_pct": best_cutoff_pct,
            "n_trades": best_cell["n_trades"],
            "net_mean_bp": best_cell["net_mean_bp"],
            "t": best_cell["t"],
            "signal_t_excess": best_cell["signal_t_excess"],
            "ci_lower_bp": best_cell["ci_lower_bp"],
            "perm_p_above": best_cell["perm_p_above"],
        }

        # ============================================================
        # STEP C — quarterly fold at best cell
        # ============================================================
        log.info("=== STEP C: quarterly fold at best cell ===")
        best_cell_full = run_cell(alt_data, alt_lookup, triggers_best,
                                  best_cell["hold"], best_cell["sl"], best_cell["tp"])
        best_nets = np.array(best_cell_full["nets"])
        best_ts_arr = pd.DatetimeIndex(pd.to_datetime(best_cell_full["ts"]))
        best_sym_arr = np.array(best_cell_full["sym"])
        best_quarterly = quarterly_stats(best_nets, best_ts_arr)
        out["step_c_quarterly_fold"] = best_quarterly
        n_q_pos = sum(1 for q in best_quarterly if isinstance(q.get("mean_bp"), float) and q.get("mean_bp", 0) > 0)
        n_q_pos_and_t = sum(1 for q in best_quarterly
                            if isinstance(q.get("mean_bp"), float) and q.get("mean_bp", 0) > 0
                            and q.get("t", 0) > 1.0)
        q1_2026_mean = next((q.get("mean_bp") for q in best_quarterly if q.get("quarter") == "2026Q1"), None)
        out["step_c_quarters_positive"] = n_q_pos
        out["step_c_quarters_positive_and_t_gt_1"] = n_q_pos_and_t
        out["step_c_2026Q1_mean_bp"] = q1_2026_mean
        for q in best_quarterly:
            log.info("  %s: n=%s mean=%s t=%s", q.get("quarter"), q.get("n"),
                     f"{q.get('mean_bp'):+.2f}" if isinstance(q.get('mean_bp'), float) else "NA",
                     f"{q.get('t'):+.2f}" if isinstance(q.get('t'), float) else "NA")

        # ============================================================
        # STEP D — per-symbol breakdown at best cell
        # ============================================================
        log.info("=== STEP D: per-symbol breakdown at best cell ===")
        per_sym = []
        n_sym_pos = 0
        n_sym_strong = 0  # signal_t_excess >= 1
        n_sym_broken = 0  # signal_t_excess < 0 OR mean<0
        # Reuse pool for the best cell's hold (without SL/TP — pool always plain hold)
        pool_best_hold = pool_by_hold.get(best_cell["hold"],
                                          build_candidate_pool(alt_data, alt_lookup,
                                                               best_cell["hold"], None, None,
                                                               n_samples=N_POOL_SAMPLES, seed=SEED))
        for sym in ALTS:
            mask = best_sym_arr == sym
            sub = best_nets[mask]
            if len(sub) < 2:
                per_sym.append({"sym": sym, "n": int(len(sub)), "note": "insufficient"})
                continue
            try:
                fe_s = fee_aware_perm_test(sub, pool_best_hold, fee_per_trade=FEE_RT,
                                           n_perms=200, rng_seed=SEED)
                sig_t_ex = fe_s.get("signal_t_excess")
            except Exception:
                sig_t_ex = None
            try:
                bs_s = bootstrap_ci(sub, n_boot=400, block_size=1, rng_seed=SEED)
                ci_lo_s = bs_s["ci_lower"] * 1e4
            except Exception:
                ci_lo_s = None
            stat = stats_block(sub)
            stat["sym"] = sym
            stat["signal_t_excess"] = sig_t_ex
            stat["ci_lower_bp"] = ci_lo_s
            per_sym.append(stat)
            if stat["mean_bp"] > 0:
                n_sym_pos += 1
            if sig_t_ex is not None and sig_t_ex >= 1.0 and stat["mean_bp"] > 0:
                n_sym_strong += 1
            if (sig_t_ex is not None and sig_t_ex < 0) or stat["mean_bp"] < 0:
                n_sym_broken += 1
        out["step_d_per_symbol"] = per_sym
        out["step_d_n_sym_pos"] = n_sym_pos
        out["step_d_n_sym_strong"] = n_sym_strong
        out["step_d_n_sym_broken"] = n_sym_broken
        log.info("Step D: %d/%d sym net_pos, %d/%d strong (sig_t_ex>=1), %d/%d broken",
                 n_sym_pos, len(ALTS), n_sym_strong, len(ALTS), n_sym_broken, len(ALTS))

        # ============================================================
        # STEP E — capacity
        # ============================================================
        log.info("=== STEP E: capacity ===")
        data_days = (btc.index[-1] - btc.index[0]).total_seconds() / 86400.0
        data_years = data_days / 365.25
        triggers_per_yr = len(triggers_best) / data_years if data_years > 0 else float("nan")
        trades_per_yr = best_cell["n_trades"] / data_years if data_years > 0 else float("nan")
        avg_concurrent = (best_cell["hold"] * len(triggers_best)) / (data_days * 24 * 60) if data_days > 0 else float("nan")
        out["step_e_capacity"] = {
            "data_days": data_days,
            "data_years": data_years,
            "triggers_total": int(len(triggers_best)),
            "trades_total": best_cell["n_trades"],
            "triggers_per_year": triggers_per_yr,
            "trades_per_year": trades_per_yr,
            "expected_avg_concurrent_positions": avg_concurrent,
            "alpha_per_sym_per_yr_bp": (best_cell["net_mean_bp"]
                                        * (best_cell["n_trades"] / len(alt_data))
                                        / data_years) if data_years > 0 else float("nan"),
        }
        log.info("Step E: data_yr=%.2f trades_total=%d trades/yr=%.0f avg_concurrent=%.3f",
                 data_years, best_cell["n_trades"], trades_per_yr, avg_concurrent)

        # ============================================================
        # STEP F — final robust stats at best cell (heavy n)
        # ============================================================
        log.info("=== STEP F: final robust stats at best cell (perm=%d, boot=%d) ===",
                 FINAL_N_PERMS, FINAL_N_BOOT)
        fe_final = fee_aware_perm_test(
            best_nets, pool_best_hold, fee_per_trade=FEE_RT,
            n_perms=FINAL_N_PERMS, rng_seed=SEED)
        # For bootstrap use block_size = hold to respect autocorrelation
        bs_final = bootstrap_ci(best_nets, n_boot=FINAL_N_BOOT,
                                block_size=best_cell["hold"], rng_seed=SEED)
        step_f = {
            "obs_mean_bp": fe_final["obs_mean"] * 1e4,
            "obs_t": fe_final["obs_t"],
            "null_mean_t": fe_final["null_mean_t"],
            "null_std_t": fe_final["null_std_t"],
            "signal_t_excess": fe_final["signal_t_excess"],
            "perm_p_one_sided_above": fe_final["perm_p_one_sided_above"],
            "perm_p_one_sided_below": fe_final["perm_p_one_sided_below"],
            "perm_p_two_sided": fe_final["perm_p_two_sided"],
            "n_observed": fe_final["n_observed"],
            "n_candidate": fe_final["n_candidate"],
            "bootstrap_block_size": best_cell["hold"],
            "bootstrap_mean_bp": bs_final["mean"] * 1e4,
            "bootstrap_ci_lower_bp": bs_final["ci_lower"] * 1e4,
            "bootstrap_ci_upper_bp": bs_final["ci_upper"] * 1e4,
            "bootstrap_prob_positive": bs_final["prob_positive"],
        }
        out["step_f_final_robust"] = step_f
        log.info("Step F: obs_t=%+.2f null_t=%+.2f sig_t_ex=%+.2f perm_p_above=%.4f ci=[%+.2f,%+.2f]bp prob_pos=%.3f",
                 step_f["obs_t"], step_f["null_mean_t"], step_f["signal_t_excess"],
                 step_f["perm_p_one_sided_above"],
                 step_f["bootstrap_ci_lower_bp"], step_f["bootstrap_ci_upper_bp"],
                 step_f["bootstrap_prob_positive"])

        # ============================================================
        # STEP G — comparison vs R-1 baseline & unfiltered
        # ============================================================
        log.info("=== STEP G: comparison summary ===")
        r1 = out["r1_baseline"]
        unfiltered_baseline_bp = r1["unfiltered_baseline_mean_bp"]
        alpha_uplift_bp = best_cell["net_mean_bp"] - unfiltered_baseline_bp
        out["step_g_comparison"] = {
            "r1_n_trades": r1["n_trades"],
            "r1_net_mean_bp": r1["net_mean_bp"],
            "r1_signal_t_excess": r1["signal_t_excess"],
            "r2_best_cell_n_trades": best_cell["n_trades"],
            "r2_best_cell_net_mean_bp": best_cell["net_mean_bp"],
            "r2_best_cell_signal_t_excess": step_f["signal_t_excess"],
            "r2_unfiltered_baseline_bp": unfiltered_baseline_bp,
            "alpha_uplift_vs_unfiltered_bp": alpha_uplift_bp,
            "improvement_vs_r1_bp": best_cell["net_mean_bp"] - r1["net_mean_bp"],
        }
        log.info("Step G: R-1=%.2fbp -> R-2_best=%.2fbp | uplift_vs_unfiltered=%.2fbp",
                 r1["net_mean_bp"], best_cell["net_mean_bp"], alpha_uplift_bp)

        # ============================================================
        # VERDICT
        # ============================================================
        criteria = {}
        sig_ex = step_f["signal_t_excess"]
        ci_lo = step_f["bootstrap_ci_lower_bp"]
        ppa = step_f["perm_p_one_sided_above"]

        criteria["best_sig_t_excess_ge_2p5"] = (sig_ex is not None and sig_ex >= 2.5)
        criteria["best_ci_lower_pos"] = (ci_lo is not None and ci_lo > 0)
        criteria["best_perm_p_above_le_0p01"] = (ppa is not None and ppa <= 0.01)
        criteria["quarters_pos_ge_3"] = (n_q_pos >= 3)
        criteria["quarter_2026Q1_mean_ge_neg10bp"] = (
            q1_2026_mean is None or (isinstance(q1_2026_mean, float) and q1_2026_mean > -10.0)
        )
        criteria["plateau_ge_10"] = (len(plateau_cells) >= 10)
        criteria["per_sym_strong_ge_10"] = (n_sym_strong >= 10)
        criteria["per_sym_net_pos_ge_10"] = (n_sym_pos >= 10)
        criteria["capacity_trades_per_yr_ge_200"] = (
            trades_per_yr is not None and trades_per_yr >= 200
        )
        criteria["alpha_uplift_ge_25bp"] = (alpha_uplift_bp >= 25.0)

        graveyard_2026Q1_killer = (isinstance(q1_2026_mean, float) and q1_2026_mean < -20.0)
        graveyard_plateau_too_thin = (len(plateau_cells) <= 5)
        graveyard_per_sym_too_few = (n_sym_pos < 8)
        graveyard_trades_too_few = (trades_per_yr is not None and trades_per_yr < 100)

        all_pass = all(criteria.values())

        if graveyard_2026Q1_killer or graveyard_plateau_too_thin or graveyard_per_sym_too_few or graveyard_trades_too_few:
            verdict = "GRAVEYARD"
        elif all_pass:
            verdict = "CANDIDATE-FOR-R3"
        else:
            # Determine if borderline conditions hold
            borderline = False
            if isinstance(q1_2026_mean, float) and -20.0 <= q1_2026_mean <= -10.0:
                borderline = True
            if 5 < len(plateau_cells) < 10:
                borderline = True
            if 8 <= n_sym_pos <= 9:
                borderline = True
            verdict = "BORDERLINE" if borderline else "FAIL"

        reasons_pass = [k for k, v in criteria.items() if v]
        reasons_fail = [k for k, v in criteria.items() if not v]

        out["criteria"] = criteria
        out["reasons_pass"] = reasons_pass
        out["reasons_fail"] = reasons_fail
        out["verdict"] = verdict

        out["wall_clock_min"] = round((time.time() - t_start) / 60, 2)
        # Strip heavy nets/sym/ts from grid output to keep JSON small
        OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
        log.info("R-2 verdict=%s written to %s in %.2f min",
                 verdict, OUT_PATH, out["wall_clock_min"])
        log.info("PASS: %s", "; ".join(reasons_pass))
        log.info("FAIL: %s", "; ".join(reasons_fail))
    finally:
        db.close()


if __name__ == "__main__":
    main()
