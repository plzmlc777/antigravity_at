"""R-2 multi-symbol robustness — btc_rv_spike_up_conditional_alt_long_240m.

R-2 spec (parent agent directive 2026-05-14)
============================================
After R-1 PASS (n=2626, net_mean=+14.4 bp, t=+2.94, signal_t_excess=+5.39,
ci_lower=+8.7 bp, perm_p_one_sided_above=0.000, H3 13/13, plateau on
[210,240,270,300]), this R-2 adds:

1. Full SL/TP/hold parameter grid (96 cells; narrows to 24 if >20 min foreground).
2. Quarterly regime fold (Q3-2025, Q4-2025, Q1-2026, Q2-2026 partial).
3. Bootstrap CI on aggregated alpha at best cell (n_boot=2000, block=240).
4. Permutation test (fee-aware) on best cell (n_perms=1000).
5. Per-symbol breakdown at best cell.
6. Capacity check (events/year, concurrent positions).

Construction (IDENTICAL to R-1)
-------------------------------
BTC 30-min realized vol z(30d) >= +2.5 rising edge + 60-min cooldown,
filter btc_ret_30m > 0 (up-trigger), LONG all 13 alts at t+1m close,
hold {180..360}m, optional SL/TP intra-hold check using ohlcv high/low.

Output
------
backend/runs/research_track/btc_rv_spike_up_conditional_alt_long_240m/r2__metrics.json
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("btc_rv_up_r2")

PARADIGM = "btc_rv_spike_up_conditional_alt_long_240m"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM
OUT_PATH = OUT_DIR / "r2__metrics.json"

BTC = "BTCUSDT"
ALTS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT", "ETHUSDT",
    "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

RV_WINDOW = 30
Z_WINDOW = 30 * 24 * 60
Z_THRESH = 2.5
COOLDOWN = 60
FEE_RT = 8e-4

# Wide grid (96 cells) — will trim if needed
HOLDS_WIDE = [180, 210, 240, 270, 300, 360]
SLS_WIDE = [None, 0.02, 0.03, 0.05]   # alt drops by X% from entry -> stop
TPS_WIDE = [None, 0.03, 0.05, 0.08]

# Narrow grid (24 cells fallback)
HOLDS_NARROW = [210, 240, 270, 300]
SLS_NARROW = [None, 0.03, 0.05]
TPS_NARROW = [None, 0.05]

# When SL hits, exit fee paid both legs => round-trip fee still 8 bp
N_PERMS = 1000
N_BOOT = 2000
POOL_SAMPLE_SIZE = 100_000
SEED = 42


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
    sig = pd.DataFrame(
        {"rv": rv, "rv_z": rv_z, "btc_ret_30m": btc_ret_30m}
    ).dropna()
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


# ---------- trade simulation with SL/TP ----------


def simulate_trade_with_sl_tp(
    high_arr: np.ndarray,
    low_arr: np.ndarray,
    close_arr: np.ndarray,
    ts_to_pos: dict,
    trig_ts,
    hold_min: int,
    sl: float | None,
    tp: float | None,
) -> tuple[float, float, str]:
    """Simulate one LONG trade. Returns (gross_ret, max_adverse_per_trade, exit_reason).

    SL/TP checked bar-by-bar from entry+1 to entry+hold_min (inclusive of exit bar).
    If both SL and TP hit on same bar, conservative: SL first (LONG, low touched).
    Adverse = max drawdown during trade (low_min/entry - 1, always <=0 for LONG).
    Returns (nan, nan, 'invalid') if entry/exit data missing.
    """
    entry_ts = trig_ts + pd.Timedelta(minutes=1)
    final_exit_ts = trig_ts + pd.Timedelta(minutes=1 + hold_min)
    ei = ts_to_pos.get(entry_ts)
    xi = ts_to_pos.get(final_exit_ts)
    if ei is None or xi is None:
        return float("nan"), float("nan"), "invalid"
    entry_p = close_arr[ei]
    if not (entry_p > 0) or np.isnan(entry_p):
        return float("nan"), float("nan"), "invalid"
    # SL/TP intra-hold scan
    bar_lows = low_arr[ei + 1 : xi + 1]
    bar_highs = high_arr[ei + 1 : xi + 1]
    bar_closes = close_arr[ei + 1 : xi + 1]
    if len(bar_closes) == 0:
        return float("nan"), float("nan"), "invalid"
    sl_price = entry_p * (1.0 - sl) if sl else None
    tp_price = entry_p * (1.0 + tp) if tp else None
    exit_reason = "time"
    exit_price = bar_closes[-1]
    cum_low = entry_p
    for k in range(len(bar_closes)):
        lo = bar_lows[k]
        hi = bar_highs[k]
        if not np.isnan(lo):
            cum_low = min(cum_low, lo)
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
    max_adverse = cum_low / entry_p - 1.0
    return float(gross), float(max_adverse), exit_reason


def simulate_grid_cell(
    alt_data: dict,
    alt_lookup: dict,
    trig_ts_list: list,
    hold_min: int,
    sl: float | None,
    tp: float | None,
) -> dict:
    """Run all (trigger × alt) trades for one cell. Return stats + per-trade arrays."""
    all_net: list[float] = []
    all_gross: list[float] = []
    all_adverse: list[float] = []
    all_exit_reason: list[str] = []
    all_trig_ts: list[pd.Timestamp] = []
    all_sym: list[str] = []
    per_sym_net: dict[str, list[float]] = {s: [] for s in alt_data}
    for sym, df_dict in alt_data.items():
        high_a = df_dict["high"]
        low_a = df_dict["low"]
        close_a = df_dict["close"]
        ts_pos = alt_lookup[sym]
        for ts in trig_ts_list:
            g, mad, er = simulate_trade_with_sl_tp(
                high_a, low_a, close_a, ts_pos, ts, hold_min, sl, tp,
            )
            if np.isnan(g):
                continue
            n = g - FEE_RT
            all_gross.append(g)
            all_net.append(n)
            all_adverse.append(mad)
            all_exit_reason.append(er)
            all_trig_ts.append(ts)
            all_sym.append(sym)
            per_sym_net[sym].append(n)
    arr = np.array(all_net)
    if len(arr) < 2:
        return {
            "n_trades": int(len(arr)), "net_mean": float("nan"),
            "t_stat": float("nan"), "win_rate": float("nan"),
            "max_adverse_mean": float("nan"), "sharpe_per_trade": float("nan"),
            "pct_sl": 0.0, "pct_tp": 0.0, "pct_time": 0.0,
            "per_sym_net": per_sym_net,
            "all_net": arr.tolist(),
            "all_trig_ts": [str(t) for t in all_trig_ts],
            "all_sym": all_sym,
        }
    mean = arr.mean()
    sd = arr.std(ddof=1)
    t = mean / sd * np.sqrt(len(arr)) if sd > 0 else 0.0
    win = float((arr > 0).mean())
    er_arr = np.array(all_exit_reason)
    return {
        "n_trades": int(len(arr)),
        "net_mean": float(mean),
        "t_stat": float(t),
        "win_rate": win,
        "max_adverse_mean": float(np.mean(all_adverse)),
        "sharpe_per_trade": float(mean / sd) if sd > 0 else 0.0,
        "pct_sl": float((er_arr == "sl").mean()),
        "pct_tp": float((er_arr == "tp").mean()),
        "pct_time": float((er_arr == "time").mean()),
        "per_sym_net": per_sym_net,
        "all_net": arr.tolist(),
        "all_trig_ts": [str(t) for t in all_trig_ts],
        "all_sym": all_sym,
    }


def candidate_pool_returns(close_arr: np.ndarray, hold_min: int,
                           stride: int = 60) -> np.ndarray:
    n = len(close_arr)
    if n <= hold_min + 1:
        return np.array([])
    ep = close_arr[: -hold_min - 1 : stride]
    xp = close_arr[hold_min + 1 :: stride]
    m = min(len(ep), len(xp))
    ep = ep[:m]
    xp = xp[:m]
    with np.errstate(divide="ignore", invalid="ignore"):
        r = (xp / ep) - 1.0
    return r[np.isfinite(r)]


def quarterly_fold(net_arr: np.ndarray, trig_ts: list) -> dict:
    """Split per-trade by trigger ts into quarters, report stats."""
    out: dict[str, dict] = {}
    if len(net_arr) == 0:
        return out
    ts_arr = pd.to_datetime(trig_ts)
    df = pd.DataFrame({"net": net_arr, "ts": ts_arr})
    df["q"] = df["ts"].dt.to_period("Q").astype(str)
    for q, g in df.groupby("q"):
        a = g["net"].to_numpy()
        if len(a) < 2:
            out[q] = {"n": int(len(a)), "mean_net": float("nan"),
                      "t": float("nan"), "win": float("nan")}
            continue
        sd = a.std(ddof=1)
        out[q] = {
            "n": int(len(a)),
            "mean_net": float(a.mean()),
            "t": float(a.mean() / sd * np.sqrt(len(a))) if sd > 0 else 0.0,
            "win": float((a > 0).mean()),
        }
    return out


def main() -> int:
    t0 = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log.info("== R-2: %s ==", PARADIGM)

    # Decide grid scope by env (allows quick narrow rerun)
    import os
    grid_mode = os.environ.get("GRID_MODE", "wide")
    if grid_mode == "narrow":
        HOLDS, SLS, TPS = HOLDS_NARROW, SLS_NARROW, TPS_NARROW
    else:
        HOLDS, SLS, TPS = HOLDS_WIDE, SLS_WIDE, TPS_WIDE
    log.info("grid mode=%s  cells=%d", grid_mode, len(HOLDS) * len(SLS) * len(TPS))

    with SessionLocal() as db:
        btc = load_ohlcv_1m(db, BTC)
        log.info("BTC: %d bars  %s -> %s", len(btc), btc.index.min(), btc.index.max())
        sig = compute_btc_signal(btc)
        triggers = extract_triggers(sig, Z_THRESH)
        log.info("up-triggers: %d", len(triggers))
        trig_ts_list = list(triggers.index)

        # Load alts (open/high/low/close)
        alt_data: dict = {}
        alt_lookup: dict = {}
        for sym in ALTS:
            df = load_ohlcv_1m(db, sym)
            if df.empty:
                log.warning("missing %s", sym)
                continue
            alt_data[sym] = {
                "high": df["high"].to_numpy(),
                "low": df["low"].to_numpy(),
                "close": df["close"].to_numpy(),
            }
            alt_lookup[sym] = {ts: i for i, ts in enumerate(df.index)}
            log.info("  %s: %d bars", sym, len(df))
        log.info("alts loaded: %d / %d", len(alt_data), len(ALTS))

    # ---- Grid search ----
    log.info("starting grid search...")
    grid_rows: list[dict] = []
    cell_payloads: dict[tuple, dict] = {}
    n_cells = len(HOLDS) * len(SLS) * len(TPS)
    cell_i = 0
    for hold in HOLDS:
        for sl in SLS:
            for tp in TPS:
                cell_i += 1
                ct0 = time.time()
                res = simulate_grid_cell(
                    alt_data, alt_lookup, trig_ts_list, hold, sl, tp,
                )
                ct = time.time() - ct0
                row = {
                    "hold": hold,
                    "sl": sl,
                    "tp": tp,
                    "n_trades": res["n_trades"],
                    "net_mean_bp": res["net_mean"] * 1e4 if not np.isnan(res["net_mean"]) else float("nan"),
                    "t": res["t_stat"],
                    "win": res["win_rate"],
                    "max_adverse_mean": res["max_adverse_mean"],
                    "sharpe_per_trade": res["sharpe_per_trade"],
                    "pct_sl": res["pct_sl"],
                    "pct_tp": res["pct_tp"],
                    "pct_time": res["pct_time"],
                }
                grid_rows.append(row)
                cell_payloads[(hold, sl, tp)] = res
                log.info(
                    "  cell %d/%d  hold=%d sl=%s tp=%s  n=%d net_bp=%.2f t=%.2f win=%.3f  [%.1fs]",
                    cell_i, n_cells, hold, sl, tp,
                    res["n_trades"], row["net_mean_bp"], row["t"], row["win"], ct,
                )
                # Time guard
                if time.time() - t0 > 18 * 60:
                    log.warning("time guard hit (>18 min), stopping grid early")
                    break
            else:
                continue
            break
        else:
            continue
        break

    grid_df = pd.DataFrame(grid_rows)
    log.info("grid done in %.1f min, cells=%d", (time.time() - t0) / 60.0, len(grid_df))

    # ---- Best cell selection (max signal: t-stat, with floor n_trades >= 1500) ----
    valid = grid_df[grid_df["n_trades"] >= 1500].copy()
    if len(valid) == 0:
        valid = grid_df.copy()
    best_idx = valid["t"].idxmax()
    best_row = grid_df.loc[best_idx].to_dict()
    # Recover exact key (None vs NaN) from cell_payloads keys
    import math
    def _match(a, b):
        if a is None and (b is None or (isinstance(b, float) and math.isnan(b))):
            return True
        if b is None and (a is None or (isinstance(a, float) and math.isnan(a))):
            return True
        return a == b
    target_h = int(best_row["hold"])
    best_key = None
    for k in cell_payloads.keys():
        if k[0] == target_h and _match(k[1], best_row["sl"]) and _match(k[2], best_row["tp"]):
            best_key = k
            break
    if best_key is None:
        raise RuntimeError(f"best_key not found for {best_row}")
    # Normalize NaN -> None for clean output
    best_row["sl"] = best_key[1]
    best_row["tp"] = best_key[2]
    log.info(
        "best cell: hold=%d sl=%s tp=%s  n=%d net_bp=%.2f t=%.2f win=%.3f",
        best_row["hold"], best_row["sl"], best_row["tp"],
        best_row["n_trades"], best_row["net_mean_bp"],
        best_row["t"], best_row["win"],
    )
    best_res = cell_payloads[best_key]
    best_net = np.array(best_res["all_net"])

    # ---- Quarterly fold at best cell ----
    qf = quarterly_fold(best_net, best_res["all_trig_ts"])
    n_q_pos = sum(1 for v in qf.values() if v.get("mean_net", 0) > 0 and v.get("t", 0) > 1.0)
    n_q_total = len(qf)
    log.info("quarterly fold: %d/%d quarters positive (mean>0 AND t>1.0)", n_q_pos, n_q_total)
    for q, v in qf.items():
        log.info("  %s  n=%d mean_bp=%.2f t=%.2f win=%.3f",
                 q, v["n"], v["mean_net"] * 1e4 if not np.isnan(v["mean_net"]) else float("nan"),
                 v["t"], v["win"])

    # ---- Bootstrap CI at best cell (block=hold) ----
    log.info("bootstrap CI (n_boot=%d, block=%d)...", N_BOOT, best_row["hold"])
    boot = bootstrap_ci(
        best_net.tolist(),
        n_boot=N_BOOT,
        block_size=int(best_row["hold"]),
        rng_seed=SEED,
    )
    log.info("  mean=%.6f  ci=[%.6f, %.6f]  prob_pos=%.4f",
             boot["mean"], boot["ci_lower"], boot["ci_upper"], boot["prob_positive"])

    # ---- Permutation test at best cell ----
    log.info("building candidate pool (hold=%d, stride=60)...", best_row["hold"])
    pool_chunks = []
    for sym, df_dict in alt_data.items():
        r = candidate_pool_returns(df_dict["close"], int(best_row["hold"]), stride=60)
        pool_chunks.append(r)
    candidate_pool = np.concatenate(pool_chunks) if pool_chunks else np.array([])
    rng_pool = np.random.default_rng(SEED)
    if len(candidate_pool) > POOL_SAMPLE_SIZE:
        candidate_pool = rng_pool.choice(
            candidate_pool, size=POOL_SAMPLE_SIZE, replace=False,
        )
    log.info("candidate pool: %d (post-sample)", len(candidate_pool))
    perm = fee_aware_perm_test(
        observed_net_returns=best_net.tolist(),
        candidate_pool_returns=candidate_pool.tolist(),
        fee_per_trade=FEE_RT,
        n_perms=N_PERMS,
        rng_seed=SEED,
    )
    log.info("  obs_t=%.4f null_mean_t=%.4f signal_t_excess=%.4f",
             perm["obs_t"], perm["null_mean_t"], perm["signal_t_excess"])
    log.info("  perm_p_two=%.4f perm_p_above=%.4f",
             perm["perm_p_two_sided"], perm["perm_p_one_sided_above"])

    # ---- Per-symbol breakdown at best cell ----
    per_sym = {}
    for sym, arr in best_res["per_sym_net"].items():
        a = np.array(arr)
        if len(a) < 2:
            per_sym[sym] = {"n": int(len(a)), "mean_net": float("nan"),
                            "t": float("nan"), "win": float("nan")}
            continue
        sd = a.std(ddof=1)
        per_sym[sym] = {
            "n": int(len(a)),
            "mean_net": float(a.mean()),
            "mean_net_bp": float(a.mean()) * 1e4,
            "t": float(a.mean() / sd * np.sqrt(len(a))) if sd > 0 else 0.0,
            "win": float((a > 0).mean()),
        }
    n_pos_sym = sum(1 for v in per_sym.values() if v.get("mean_net", 0) > 0)
    log.info("per-sym: %d/%d alts with mean_net > 0", n_pos_sym, len(per_sym))

    # ---- Plateau detection (>=3 adjacent cells with t>=2.0) ----
    # Adjacent: same SL+TP, neighboring hold values
    plateau_groups = []
    for sl in SLS:
        for tp in TPS:
            sub = grid_df[(grid_df["sl"].apply(lambda x: (x is sl) or (x == sl)))
                          & (grid_df["tp"].apply(lambda x: (x is tp) or (x == tp)))]
            sub = sub.sort_values("hold")
            run = []
            for _, r in sub.iterrows():
                if r["t"] >= 2.0:
                    run.append((int(r["hold"]), float(r["t"]), float(r["net_mean_bp"])))
                    if len(run) >= 3:
                        plateau_groups.append({"sl": sl, "tp": tp, "run": list(run)})
                else:
                    run = []
    log.info("plateau groups (>=3 adj cells t>=2.0): %d", len(plateau_groups))

    # ---- Capacity check ----
    btc_span_days = (btc.index.max() - btc.index.min()).days
    n_trig_per_year = len(trig_ts_list) / (btc_span_days / 365.25)
    # Concurrent positions: count how many trig_ts have another trig within hold window
    overlap_count = 0
    for i, ts in enumerate(trig_ts_list):
        window_end = ts + pd.Timedelta(minutes=best_row["hold"])
        # count next triggers within window
        for j in range(i + 1, len(trig_ts_list)):
            if trig_ts_list[j] <= window_end:
                overlap_count += 1
            else:
                break
    avg_concurrent = overlap_count / max(1, len(trig_ts_list))
    capacity = {
        "data_span_days": int(btc_span_days),
        "n_triggers_total": int(len(trig_ts_list)),
        "triggers_per_year": float(n_trig_per_year),
        "trades_per_year_est": float(n_trig_per_year * len(alt_data)),
        "avg_concurrent_positions": float(avg_concurrent),
        "note": "8bp round-trip fee assumed; real slippage on 13-alt fan-out untested",
    }
    log.info("capacity: %.1f triggers/yr  %.1f trades/yr  avg_concurrent=%.2f",
             n_trig_per_year, n_trig_per_year * len(alt_data), avg_concurrent)

    # ---- PASS criteria ----
    crit = {
        "signal_t_excess_ge_2p5": bool(perm["signal_t_excess"] >= 2.5),
        "ci_lower_positive": bool(boot["ci_lower"] > 0),
        "perm_p_above_le_0p01": bool(perm["perm_p_one_sided_above"] <= 0.01),
        "quarterly_3_of_4_pos": bool(n_q_pos >= 3 and n_q_total >= 3),
        "plateau_present": bool(len(plateau_groups) >= 1),
        "per_sym_ge_10_of_13": bool(n_pos_sym >= 10),
    }
    n_pass = sum(crit.values())
    if n_pass == 6:
        verdict = "PASS"
    elif n_pass >= 4 and crit["plateau_present"] and crit["ci_lower_positive"]:
        verdict = "BORDERLINE"
    else:
        verdict = "GRAVEYARD"
    verdict_reasons = [k for k, v in crit.items() if not v]
    log.info("VERDICT: %s  (pass %d/6)  failing: %s", verdict, n_pass, verdict_reasons)

    # Top 5 grid cells (normalize NaN sl/tp -> None)
    import math
    def _denan(v):
        return None if (isinstance(v, float) and math.isnan(v)) else v
    top5 = grid_df.sort_values("t", ascending=False).head(5).to_dict(orient="records")
    for r in top5:
        r["sl"] = _denan(r["sl"])
        r["tp"] = _denan(r["tp"])
    for r in grid_rows:
        r["sl"] = _denan(r["sl"])
        r["tp"] = _denan(r["tp"])

    out = {
        "paradigm": PARADIGM,
        "verdict": verdict,
        "verdict_reasons": verdict_reasons,
        "criteria_passed": crit,
        "n_pass": n_pass,
        "data_window": {
            "btc_first": str(btc.index.min()),
            "btc_last": str(btc.index.max()),
            "btc_bars": int(len(btc)),
            "alts_loaded": list(alt_data.keys()),
        },
        "config": {
            "rv_window_bars": RV_WINDOW,
            "z_window_bars": Z_WINDOW,
            "z_thresh": Z_THRESH,
            "cooldown_min": COOLDOWN,
            "fee_round_trip": FEE_RT,
            "grid_mode": grid_mode,
            "holds": HOLDS,
            "sls": SLS,
            "tps": TPS,
            "n_perms": N_PERMS,
            "n_boot": N_BOOT,
            "pool_sample_size": POOL_SAMPLE_SIZE,
        },
        "n_triggers": int(len(trig_ts_list)),
        "grid": grid_rows,
        "top5_by_t": top5,
        "best_cell": {
            "hold": int(best_row["hold"]),
            "sl": best_row["sl"],
            "tp": best_row["tp"],
            "n_trades": int(best_row["n_trades"]),
            "net_mean_bp": float(best_row["net_mean_bp"]),
            "t": float(best_row["t"]),
            "win_rate": float(best_row["win"]),
            "max_adverse_mean": float(best_row["max_adverse_mean"]),
            "sharpe_per_trade": float(best_row["sharpe_per_trade"]),
            "pct_sl": float(best_row["pct_sl"]),
            "pct_tp": float(best_row["pct_tp"]),
            "pct_time": float(best_row["pct_time"]),
        },
        "best_cell_perm": {
            "obs_mean": perm["obs_mean"],
            "obs_t": perm["obs_t"],
            "null_mean_t": perm["null_mean_t"],
            "null_std_t": perm["null_std_t"],
            "signal_t_excess": perm["signal_t_excess"],
            "perm_p_two_sided": perm["perm_p_two_sided"],
            "perm_p_one_sided_above": perm["perm_p_one_sided_above"],
            "perm_p_one_sided_below": perm["perm_p_one_sided_below"],
            "n_observed": perm["n_observed"],
            "n_candidate": perm["n_candidate"],
        },
        "best_cell_bootstrap": {
            "mean": boot["mean"],
            "mean_bp": boot["mean"] * 1e4,
            "ci_lower": boot["ci_lower"],
            "ci_upper": boot["ci_upper"],
            "ci_lower_bp": boot["ci_lower"] * 1e4,
            "ci_upper_bp": boot["ci_upper"] * 1e4,
            "prob_positive": boot["prob_positive"],
            "n": boot["n"],
            "n_boot": N_BOOT,
            "block_size": int(best_row["hold"]),
        },
        "quarterly_fold": qf,
        "n_quarters_positive": int(n_q_pos),
        "n_quarters_total": int(n_q_total),
        "per_symbol_best_cell": per_sym,
        "n_alts_positive": int(n_pos_sym),
        "plateau_groups": plateau_groups,
        "capacity": capacity,
        "wall_clock_min": (time.time() - t0) / 60.0,
    }

    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    log.info("written: %s", OUT_PATH)
    log.info("== R-2 done in %.1f min  verdict=%s ==",
             (time.time() - t0) / 60.0, verdict)
    return 0


if __name__ == "__main__":
    sys.exit(main())
