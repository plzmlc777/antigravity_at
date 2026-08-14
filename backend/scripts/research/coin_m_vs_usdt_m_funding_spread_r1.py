"""Paradigm 225 R-1 PoC.

Hypothesis: COIN-M vs USDT-M funding rate inter-class spread |z|>=1.5 signals
sophisticated capital vs retail speculator positioning divergence -> directional
continuation.

Design:
- 5 syms: BTC/ETH/BNB/XRP/ADA (COIN-M PERP vs USDT-M).
- 8h cadence funding events, per-sym 30d rolling z-score (90 obs) of spread.
- 4-quadrant Symmetric Negative Test (Lesson #19):
    A_focus:  z >= +1.5 -> LONG
    A_mirror: z >= +1.5 -> SHORT
    B_focus:  z <= -1.5 -> SHORT
    B_mirror: z <= -1.5 -> LONG
- Hold sweep 4h/8h/12h/24h/48h. 24h designated PRIMARY for life-changing 4-dim.
- Era stratification (Item 6, Pattern P1 check).
- Concentration Gate (Lesson #16, strict 50% ci_pos for narrow universe).
- Life-changing 4-dim at primary hold.

Substrate:
- COIN-M funding: backend/runs/research_track/coin_m_vs_usdt_m_funding_spread/coinm_raw/
- USDT-M funding: PostgreSQL binance_funding_rate
- OHLCV 1m joblib cache: backend/runs/ohlcv_cache/{SYM}USDT_1m.joblib

Outputs:
- backend/runs/research_track/coin_m_vs_usdt_m_funding_spread/r1__metrics.json
- backend/runs/research_track/coin_m_vs_usdt_m_funding_spread/r1__verdict.md
"""
from __future__ import annotations
import json
import logging
import os
import sys
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import psycopg2

sys.path.insert(0, str(Path(__file__).parent))
from _perm_utils import fee_aware_perm_test, bootstrap_ci

LOG = logging.getLogger("paradigm225.r1")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")

ROOT = Path("backend/runs/research_track/coin_m_vs_usdt_m_funding_spread")
COINM_ROOT = ROOT / "coinm_raw"
ART = ROOT / "artifacts"
CACHE_DIR = Path("backend/runs/ohlcv_cache")
ART.mkdir(parents=True, exist_ok=True)

PAIRS = [
    ("BTCUSD_PERP", "BTCUSDT"),
    ("ETHUSD_PERP", "ETHUSDT"),
    ("BNBUSD_PERP", "BNBUSDT"),
    ("XRPUSD_PERP", "XRPUSDT"),
    ("ADAUSD_PERP", "ADAUSDT"),
]

THRESHOLD = 1.5
ZWIN = 90
HOLDS_HOURS = [4, 8, 12, 24, 48]
PRIMARY_HOLD = 24
FEE_ROUND_TRIP = 0.0008  # 4bp taker each side


def load_coinm(sym: str) -> pd.DataFrame:
    files = sorted((COINM_ROOT / sym).glob("*.zip"))
    frames = []
    for f in files:
        with zipfile.ZipFile(f) as z:
            for name in z.namelist():
                if name.endswith(".csv"):
                    with z.open(name) as fh:
                        frames.append(pd.read_csv(fh))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df["ts"] = pd.to_datetime(df["calc_time"], unit="ms", utc=True).dt.tz_convert(None)
    df["rate"] = df["last_funding_rate"].astype(float)
    df["ts"] = df["ts"].dt.round("8h")
    return df[["ts", "rate"]].drop_duplicates("ts").sort_values("ts")


def load_usdtm(sym: str) -> pd.DataFrame:
    conn = psycopg2.connect(host="localhost",
                            database=os.getenv("POSTGRES_DB", "antigravity"),
                            user=os.getenv("POSTGRES_USER", "antigravity"),
                            password=os.getenv("POSTGRES_PASSWORD", "antigravity"))
    df = pd.read_sql(
        "SELECT funding_time AS ts, funding_rate::float AS rate FROM binance_funding_rate "
        "WHERE symbol=%s ORDER BY funding_time", conn, params=(sym,))
    conn.close()
    df["ts"] = pd.to_datetime(df["ts"]).dt.round("8h")
    return df.drop_duplicates("ts").sort_values("ts")


def load_ohlcv_1m(sym: str) -> pd.DataFrame:
    import joblib
    path = CACHE_DIR / f"{sym}_1m.joblib"
    if not path.exists():
        raise FileNotFoundError(f"OHLCV cache missing: {path}")
    df = joblib.load(path)
    if "ts" not in df.columns:
        # try common index names
        if isinstance(df.index, pd.DatetimeIndex):
            df = df.reset_index().rename(columns={df.index.name or "index": "ts"})
    df["ts"] = pd.to_datetime(df["ts"]).astype("datetime64[ns]")
    # ensure sorted
    df = df.sort_values("ts").drop_duplicates("ts")
    return df[["ts", "close"]]


def build_spread_z(cm: pd.DataFrame, um: pd.DataFrame) -> pd.DataFrame:
    start = pd.Timestamp("2024-01-01")
    end = pd.Timestamp("2026-05-16")
    cm = cm[(cm["ts"] >= start) & (cm["ts"] <= end)]
    um = um[(um["ts"] >= start) & (um["ts"] <= end)]
    m = pd.merge(cm.rename(columns={"rate": "cm_rate"}),
                 um.rename(columns={"rate": "um_rate"}),
                 on="ts", how="inner").sort_values("ts")
    m["spread"] = m["cm_rate"] - m["um_rate"]
    m["mu"] = m["spread"].rolling(ZWIN, min_periods=ZWIN).mean()
    m["sd"] = m["spread"].rolling(ZWIN, min_periods=ZWIN).std()
    m["z"] = (m["spread"] - m["mu"]) / m["sd"]
    return m.dropna(subset=["z"]).reset_index(drop=True)


def forward_ret(px: pd.DataFrame, entry_ts: pd.Timestamp, hold_h: int) -> float:
    """Return log-return from entry_ts to entry_ts+hold_h using close-of-minute px."""
    # px is 1m: find nearest minute >= entry_ts as entry, then +hold_h.
    entry = px[px["ts"] >= entry_ts].head(1)
    exit_ts = entry_ts + pd.Timedelta(hours=hold_h)
    exit = px[px["ts"] >= exit_ts].head(1)
    if entry.empty or exit.empty:
        return np.nan
    e = float(entry["close"].iloc[0])
    x = float(exit["close"].iloc[0])
    if e <= 0 or x <= 0:
        return np.nan
    return (x / e) - 1.0


def build_candidate_pool_returns(px: pd.DataFrame, evt_ts: pd.Series, hold_h: int, stride_min: int = 60) -> np.ndarray:
    """Build a candidate pool of forward returns at fixed stride entry points
    across the full period (used as fee-drift baseline for perm_test).
    """
    if px.empty or evt_ts.empty:
        return np.array([])
    tmin = evt_ts.min() - pd.Timedelta(days=1)
    tmax = evt_ts.max() + pd.Timedelta(days=1)
    px_r = px[(px["ts"] >= tmin) & (px["ts"] <= tmax)].reset_index(drop=True)
    if len(px_r) < 2:
        return np.array([])
    # sample every stride_min
    px_r["min_of_period"] = ((px_r["ts"].astype("int64") // 60_000_000_000) - (px_r["ts"].iloc[0].value // 60_000_000_000))
    px_r = px_r[(px_r["min_of_period"] % stride_min) == 0].reset_index(drop=True)
    # forward return
    px_r["close_fut"] = px_r["close"].shift(-hold_h * 60 // stride_min)
    px_r["fret"] = (px_r["close_fut"] / px_r["close"]) - 1.0
    return px_r["fret"].dropna().values


def event_forward_returns(px: pd.DataFrame, evt_ts_list: List[pd.Timestamp], hold_h: int, direction: int) -> np.ndarray:
    """Vectorized forward-return computation for a list of entry timestamps.
    direction: +1 for LONG, -1 for SHORT.
    """
    if not evt_ts_list:
        return np.array([])
    px_sorted = px.sort_values("ts").reset_index(drop=True)
    px_sorted["ts_i64"] = px_sorted["ts"].astype("int64")
    ts_arr = px_sorted["ts_i64"].values
    close_arr = px_sorted["close"].values

    hold_ns = hold_h * 3600 * 10**9
    rets = []
    for t in evt_ts_list:
        t_ns = int(pd.Timestamp(t).value)
        i_ent = np.searchsorted(ts_arr, t_ns, side="left")
        i_ext = np.searchsorted(ts_arr, t_ns + hold_ns, side="left")
        if i_ent >= len(ts_arr) or i_ext >= len(ts_arr):
            continue
        e = close_arr[i_ent]
        x = close_arr[i_ext]
        if e > 0 and x > 0:
            gross = (x / e - 1.0) * direction
            rets.append(gross)
    return np.array(rets, dtype=float)


def era_of(ts: pd.Timestamp) -> str:
    y = ts.year
    h = 1 if ts.month <= 6 else 2
    return f"{y}H{h}"


def quarter_of(ts: pd.Timestamp) -> str:
    return f"{ts.year}Q{(ts.month - 1) // 3 + 1}"


def eval_quadrant(quadrant_name: str, cond_fn, direction: int,
                   spread_per_sym: Dict[str, pd.DataFrame],
                   px_per_sym: Dict[str, pd.DataFrame], hold_h: int) -> Dict:
    """Evaluate one quadrant: gather event entries per sym, compute net rets,
    perm_p, bootstrap, and per-sym / per-era / per-quarter breakdown."""
    all_net_rets = []
    per_sym_rets = {}
    per_era_rets = {}
    per_quarter_rets = {}
    events_meta = []
    candidate_pool = []

    for cm_sym, um_sym in PAIRS:
        m = spread_per_sym.get(cm_sym)
        px = px_per_sym.get(um_sym)
        if m is None or px is None or m.empty or px.empty:
            continue
        mask = cond_fn(m["z"])
        evts = m.loc[mask, "ts"].tolist()
        if not evts:
            continue
        gross = event_forward_returns(px, evts, hold_h, direction)
        if len(gross) == 0:
            continue
        net = gross - FEE_ROUND_TRIP
        per_sym_rets[um_sym] = net.tolist()
        all_net_rets.extend(net.tolist())
        # meta for era/quarter
        for t, r in zip(evts[:len(net)], net):
            events_meta.append((um_sym, t, r))
        # candidate pool (fee-drift): use every 8h evenly-spaced hold-window forward return
        cpool = build_candidate_pool_returns(px, m["ts"], hold_h, stride_min=60)
        # if direction is short, negate to get short-return pool
        if direction == -1:
            cpool = -cpool
        candidate_pool.extend(cpool.tolist())

    for um, t, r in events_meta:
        per_era_rets.setdefault(era_of(t), []).append(r)
        per_quarter_rets.setdefault(quarter_of(t), []).append(r)

    all_net = np.array(all_net_rets, dtype=float)
    result = {
        "quadrant": quadrant_name,
        "hold_h": hold_h,
        "n_events": int(len(all_net)),
        "n_syms": int(len(per_sym_rets)),
    }
    if len(all_net) < 30:
        result["verdict"] = "INSUFFICIENT_N"
        return result

    # fee-aware perm test
    if len(candidate_pool) < 2 * len(all_net):
        # oversample
        pass
    pool = np.array(candidate_pool, dtype=float) if candidate_pool else np.array([])
    if len(pool) < 2 * len(all_net):
        # fall back with less strict perm
        perm = {"signal_t_excess": float("nan"), "perm_p_two_sided": float("nan"),
                "obs_t": float("nan"), "null_mean_t": float("nan"),
                "n_candidate": int(len(pool))}
    else:
        # returns already net of fee for observed; perm test expects GROSS pool + adds fee
        pool_gross = pool + FEE_ROUND_TRIP  # undo fee since we already applied to obs
        perm = fee_aware_perm_test(all_net, pool_gross, fee_per_trade=FEE_ROUND_TRIP, n_perms=1000, rng_seed=42)

    boot = bootstrap_ci(all_net, n_boot=2000, block_size=1, alpha=0.05, rng_seed=42)

    # Per-symbol bootstrap
    per_sym_boot = {}
    n_ci_pos = 0
    for s, r in per_sym_rets.items():
        b = bootstrap_ci(r, n_boot=1000, block_size=1, alpha=0.05, rng_seed=42)
        per_sym_boot[s] = {"n": len(r), "mean_bp": round(b["mean"] * 1e4, 2),
                          "ci_lower_bp": round(b["ci_lower"] * 1e4, 2) if not np.isnan(b["ci_lower"]) else None,
                          "ci_upper_bp": round(b["ci_upper"] * 1e4, 2) if not np.isnan(b["ci_upper"]) else None}
        if b["ci_lower"] > 0:
            n_ci_pos += 1

    ci_pos_ratio = n_ci_pos / max(1, len(per_sym_rets))
    n_syms_ci_pos = n_ci_pos

    # Per-quarter t-stats
    per_quarter_t = {}
    for q, r in per_quarter_rets.items():
        r = np.array(r, dtype=float)
        if len(r) >= 5 and r.std(ddof=1) > 0:
            per_quarter_t[q] = float(r.mean() / r.std(ddof=1) * np.sqrt(len(r)))
    n_q_measurable = len(per_quarter_t)
    n_q_pos_t = sum(1 for t in per_quarter_t.values() if t > 0)
    q_pos_t_ratio = n_q_pos_t / max(1, n_q_measurable)

    # Per-era stats (Item 6 Pattern P1)
    per_era_summary = {}
    for e, r in per_era_rets.items():
        r = np.array(r, dtype=float)
        if len(r) >= 5:
            per_era_summary[e] = {
                "n": len(r), "mean_bp": round(r.mean() * 1e4, 2),
                "t": float(r.mean() / r.std(ddof=1) * np.sqrt(len(r))) if r.std(ddof=1) > 0 else 0.0
            }

    result.update({
        "mean_bp": round(float(all_net.mean()) * 1e4, 2),
        "obs_t": round(perm.get("obs_t", float("nan")), 3) if not np.isnan(perm.get("obs_t", float("nan"))) else None,
        "signal_t_excess": round(perm.get("signal_t_excess", float("nan")), 3) if not np.isnan(perm.get("signal_t_excess", float("nan"))) else None,
        "perm_p": round(perm.get("perm_p_two_sided", float("nan")), 4) if not np.isnan(perm.get("perm_p_two_sided", float("nan"))) else None,
        "ci_lower_bp": round(boot["ci_lower"] * 1e4, 2) if not np.isnan(boot["ci_lower"]) else None,
        "ci_upper_bp": round(boot["ci_upper"] * 1e4, 2) if not np.isnan(boot["ci_upper"]) else None,
        "n_syms_ci_pos": int(n_syms_ci_pos),
        "ci_pos_ratio": round(ci_pos_ratio, 3),
        "quarter_pos_t_ratio": round(q_pos_t_ratio, 3),
        "n_q_measurable": int(n_q_measurable),
        "per_symbol_bootstrap": per_sym_boot,
        "per_quarter_t": {k: round(v, 3) for k, v in per_quarter_t.items()},
        "per_era_summary": per_era_summary,
    })

    # Three-gate PASS
    three_gate = (
        (result["signal_t_excess"] is not None and result["signal_t_excess"] >= 2.0) and
        (result["ci_lower_bp"] is not None and result["ci_lower_bp"] > 0) and
        (result["perm_p"] is not None and result["perm_p"] <= 0.10)
    )
    # Concentration (strict 50% for 5 syms)
    conc_gate = (result["ci_pos_ratio"] >= 0.5 and result["quarter_pos_t_ratio"] >= 0.5 and result["n_syms_ci_pos"] >= 3)
    result["three_gate_pass"] = bool(three_gate)
    result["concentration_gate_pass"] = bool(conc_gate)

    # Pattern P1 check on era summary (monotonic decay 2024H1 -> 2026H1)
    era_order = ["2024H1", "2024H2", "2025H1", "2025H2", "2026H1"]
    ts_series = [per_era_summary[e]["t"] for e in era_order if e in per_era_summary]
    is_monotonic = len(ts_series) >= 4 and all(ts_series[i] >= ts_series[i + 1] for i in range(len(ts_series) - 1))
    result["pattern_p1_monotonic_decay"] = bool(is_monotonic and (ts_series[0] > 0 and ts_series[-1] <= 0))

    # Life-changing 4-dim (only at PRIMARY hold)
    if hold_h == PRIMARY_HOLD:
        n_trades = len(all_net)
        # trades/yr aggregate over ~2.25yr
        yrs = 2.25
        trades_per_yr = n_trades / yrs
        edge = float(all_net.mean())
        sd = float(all_net.std(ddof=1)) if len(all_net) > 1 else 1e-9
        sharpe_per_trade = edge / sd if sd > 0 else 0
        # annualize: sqrt(trades_per_yr)
        sharpe_ann = sharpe_per_trade * np.sqrt(trades_per_yr) if trades_per_yr > 0 else 0
        # capital util: avg positions held / total time. Approx: n_trades * hold_h / total_h
        total_h = yrs * 8760
        util = n_trades * hold_h / total_h
        life = {
            "trades_per_yr": round(trades_per_yr, 1),
            "edge_per_trade_bp": round(edge * 1e4, 2),
            "sharpe_ann": round(sharpe_ann, 2),
            "capital_util": round(util, 3),
            "gate_trades_yr_pass": trades_per_yr >= 52,
            "gate_edge_pass": edge >= 0.02,   # 2%/trade
            "gate_sharpe_pass": sharpe_ann >= 1.5,
            "gate_util_pass": util >= 0.30,
        }
        life["all4_pass"] = all([life["gate_trades_yr_pass"], life["gate_edge_pass"],
                                 life["gate_sharpe_pass"], life["gate_util_pass"]])
        result["life_changing_4dim"] = life

    return result


def main():
    LOG.info("Loading COIN-M funding rates...")
    coinm_data = {sym: load_coinm(sym) for sym, _ in PAIRS}
    LOG.info("Loading USDT-M funding rates...")
    usdtm_data = {um: load_usdtm(um) for _, um in PAIRS}

    LOG.info("Building per-sym spread + z...")
    spread_per_sym = {}
    for cm_sym, um_sym in PAIRS:
        m = build_spread_z(coinm_data[cm_sym], usdtm_data[um_sym])
        spread_per_sym[cm_sym] = m
        LOG.info("  %s -> n_events_zvalid=%d", cm_sym, len(m))

    LOG.info("Loading OHLCV 1m caches...")
    px_per_sym = {}
    for _, um_sym in PAIRS:
        try:
            px_per_sym[um_sym] = load_ohlcv_1m(um_sym)
            LOG.info("  %s -> %d 1m bars", um_sym, len(px_per_sym[um_sym]))
        except Exception as e:
            LOG.warning("  %s cache missing: %s", um_sym, e)

    quadrants = [
        ("A_focus_z_ge_1.5_LONG",  lambda z: z >= THRESHOLD, +1),
        ("A_mirror_z_ge_1.5_SHORT", lambda z: z >= THRESHOLD, -1),
        ("B_focus_z_le_-1.5_SHORT", lambda z: z <= -THRESHOLD, -1),
        ("B_mirror_z_le_-1.5_LONG", lambda z: z <= -THRESHOLD, +1),
    ]

    all_results = {}
    for hold_h in HOLDS_HOURS:
        LOG.info("=== hold_h=%dh ===", hold_h)
        for qname, cond, direction in quadrants:
            LOG.info("  quadrant %s ...", qname)
            r = eval_quadrant(qname, cond, direction, spread_per_sym, px_per_sym, hold_h)
            all_results[f"{qname}__{hold_h}h"] = r
            if r.get("n_events", 0) >= 30:
                LOG.info("    n=%d mean_bp=%s sigex=%s ci_lo=%s perm_p=%s three_gate=%s conc=%s",
                         r["n_events"], r.get("mean_bp"), r.get("signal_t_excess"),
                         r.get("ci_lower_bp"), r.get("perm_p"),
                         r.get("three_gate_pass"), r.get("concentration_gate_pass"))
            else:
                LOG.info("    n=%d INSUFFICIENT", r.get("n_events", 0))

    # top-level verdict
    focus_primary_keys = [f"A_focus_z_ge_1.5_LONG__{PRIMARY_HOLD}h",
                          f"B_focus_z_le_-1.5_SHORT__{PRIMARY_HOLD}h"]
    mirror_primary_keys = [f"A_mirror_z_ge_1.5_SHORT__{PRIMARY_HOLD}h",
                           f"B_mirror_z_le_-1.5_LONG__{PRIMARY_HOLD}h"]

    any_focus_pass = any(all_results.get(k, {}).get("three_gate_pass", False) for k in focus_primary_keys)
    any_mirror_pass = any(all_results.get(k, {}).get("three_gate_pass", False) for k in mirror_primary_keys)
    any_conc_pass = any(all_results.get(k, {}).get("concentration_gate_pass", False) for k in focus_primary_keys)
    any_life_pass = any(all_results.get(k, {}).get("life_changing_4dim", {}).get("all4_pass", False) for k in focus_primary_keys)
    any_p1 = any(all_results.get(k, {}).get("pattern_p1_monotonic_decay", False) for k in focus_primary_keys + mirror_primary_keys)

    # Sweep all cells for cross-hold PASS
    any_cell_three_gate = False
    for k, r in all_results.items():
        if r.get("three_gate_pass", False):
            any_cell_three_gate = True
            break

    verdict = "R1_PASS" if (any_focus_pass and any_conc_pass and any_life_pass and not any_p1) else \
              "MIRROR_MECHANISM_INVERTED" if any_mirror_pass and not any_focus_pass else \
              "PATTERN_P1_ALPHA_DECAY" if any_p1 else \
              "R1_FAIL_LIFE_CHANGING" if any_focus_pass and any_conc_pass and not any_life_pass else \
              "R1_FAIL_CONCENTRATION" if any_focus_pass and not any_conc_pass else \
              "BROAD_FALSIFIED"

    summary = {
        "paradigm_number": 225,
        "paradigm_name": "coin_m_vs_usdt_m_funding_spread_miner_vs_speculator_momentum",
        "phase": "R-1",
        "threshold": THRESHOLD,
        "primary_hold_h": PRIMARY_HOLD,
        "syms_used": [p[1] for p in PAIRS],
        "n_syms_used": len(PAIRS),
        "fee_round_trip": FEE_ROUND_TRIP,
        "verdict": verdict,
        "any_focus_three_gate_pass": any_focus_pass,
        "any_mirror_three_gate_pass": any_mirror_pass,
        "any_concentration_pass": any_conc_pass,
        "any_life_changing_pass": any_life_pass,
        "any_pattern_p1": any_p1,
        "any_cell_three_gate": any_cell_three_gate,
        "cells": all_results,
    }

    out_json = ROOT / "r1__metrics.json"
    out_json.write_text(json.dumps(summary, indent=2, default=str))
    LOG.info("wrote %s", out_json)
    print(json.dumps({k: v for k, v in summary.items() if k != "cells"}, indent=2))
    print(f"\nverdict: {verdict}")


if __name__ == "__main__":
    main()
