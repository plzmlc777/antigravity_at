"""paradigm 210 R-1 PoC — Binance USDC vs USDT perp cross-quote spread z-score

Hypothesis
----------
Same-exchange (Binance Futures), same-base-asset, different-quote (USDC vs USDT)
perp price spread z-score spike to |z|>=2 over 30d rolling window mean-reverts
within 4h. Trade the USDT-quoted contract.

Mechanism: cross-quote liquidity arbitrage path dislocation
- USDT-USDC stablecoin path: Curve/Uniswap V3 + CEX OTC desks
- When USDC-quoted perp deviates from USDT-quoted perp on Binance, arbers route
  through stablecoin pair to close the gap. Typically resolves within hours.

Family-distinct from cross-exchange (paradigm 103/104/166/187/209):
- Same exchange (no venue arbitrage fee floor)
- Different mechanism (stablecoin liquidity flow vs cross-venue OI/funding)
- D2 universe dimension: same-venue cross-quote (NEW)

R-1 protocol
------------
- Universe: 10 top-liquidity USDC/USDT paired (BTC/ETH/BNB/SOL/XRP/DOGE/LINK/SUI/ORDI/1000PEPE)
- Window: 2024-01-15 to 2026-05-20 (~860 days, 4h bars)
- Signal: z-score of (USDC_close - USDT_close) / USDT_close over 30d rolling window
- Trigger: |z| >= 2.0 (mean-reversion entry)
- 4-quadrant SNT (Lesson #19):
    A focus: z >= +2  -> SHORT USDT (USDC bid premium -> expect mean-revert down)
    A mirror: z <= -2 -> LONG  USDT (USDC ask discount -> expect mean-revert up)
    B same-sign: z >= +2 -> LONG  USDT (anti-hypothesis: continuation)
    B mirror: z <= -2 -> SHORT USDT (anti-hypothesis: continuation)
- Hold: 4h (1 forward bar) primary, sweep 4/8/12/24h
- Fee: 16 bps round-trip (8 bps each side, taker)
- Three-gate: signal_t_excess >= 2.0 AND ci_lower > 0 AND perm_p <= 0.10
- Concentration: per-quarter t-stat + per-symbol bootstrap CI
- Era stratify: 2024 / 2025 / 2026 (Item 6 alpha decay 5-pattern)
- Cross-set asymmetry (Item 7): focus vs mirror magnitude ratio
- Unconditional baseline (Lesson #39 sub-class B avoidance)
- Hold sweep (Lesson #37): 4h / 8h / 12h / 24h verdict scan

Substrate: Binance Futures klines REST archive (no freemium, no auth required)
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd
import requests

# Add backend to sys.path for _perm_utils import
BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

from scripts.research._perm_utils import bootstrap_ci, fee_aware_perm_test  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("paradigm_210_r1")

PARADIGM_NAME = "paradigm_210_alt_per_sym_binance_usdc_vs_usdt_perp_cross_quote_spread_z_directional_4h"
OUTPUT_DIR = BACKEND_DIR / "runs" / "research_track" / PARADIGM_NAME
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

UNIVERSE_BASE = [
    "BTC", "ETH", "BNB", "SOL", "XRP",
    "DOGE", "LINK", "SUI", "ORDI", "1000PEPE",
]
INTERVAL = "4h"
INTERVAL_MS = 4 * 60 * 60 * 1000
START_DATE = datetime(2024, 1, 15, tzinfo=timezone.utc)
END_DATE = datetime(2026, 5, 20, tzinfo=timezone.utc)
ROLLING_WINDOW = 30 * 6  # 30 days * 6 bars/day = 180 bars
Z_THRESHOLD = 2.0
FEE_RT = 0.0008 * 2  # 16 bps round-trip (taker both sides)
HOLD_SWEEP_BARS = [1, 2, 3, 6]  # 4h, 8h, 12h, 24h forward hold
PRIMARY_HOLD = 1  # 4h


def _ts_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _fmt(v, fmt="+.2f"):
    """Safe format helper for None/NaN values in log lines."""
    if v is None:
        return "None"
    try:
        if isinstance(v, float) and np.isnan(v):
            return "NaN"
        return f"{v:{fmt}}"
    except (TypeError, ValueError):
        return str(v)


def _fetch_klines(symbol: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    """Fetch 4h klines from Binance Futures REST in pages of 1500."""
    base = "https://fapi.binance.com/fapi/v1/klines"
    all_rows = []
    cur = start_ms
    while cur < end_ms:
        params = {
            "symbol": symbol,
            "interval": INTERVAL,
            "startTime": cur,
            "endTime": end_ms,
            "limit": 1500,
        }
        rows = None
        for attempt in range(3):
            try:
                r = requests.get(base, params=params, timeout=20)
                r.raise_for_status()
                rows = r.json()
                break
            except Exception as e:
                log.warning(f"{symbol} fetch attempt {attempt+1} err {e}; sleeping 2s")
                time.sleep(2)
        if rows is None:
            log.error(f"{symbol} fetch FAIL at cur={cur}")
            break
        if not rows:
            break
        all_rows.extend(rows)
        last_open = rows[-1][0]
        cur = last_open + INTERVAL_MS
        if len(rows) < 1500:
            break
        time.sleep(0.15)  # rate-limit polite
    if not all_rows:
        return pd.DataFrame()
    df = pd.DataFrame(all_rows, columns=[
        "open_time", "open", "high", "low", "close", "vol",
        "close_time", "quote_vol", "trades", "taker_buy_base", "taker_buy_quote", "ignore",
    ])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    for c in ["open", "high", "low", "close", "vol", "quote_vol"]:
        df[c] = df[c].astype(float)
    df = df.set_index("open_time").sort_index()
    return df[~df.index.duplicated(keep="first")]


def load_paired_panel() -> Dict[str, pd.DataFrame]:
    panel: Dict[str, pd.DataFrame] = {}
    start_ms = _ts_ms(START_DATE)
    end_ms = _ts_ms(END_DATE)
    for base in UNIVERSE_BASE:
        sym_usdt = f"{base}USDT"
        sym_usdc = f"{base}USDC"
        log.info(f"fetching {sym_usdt} ...")
        df_usdt = _fetch_klines(sym_usdt, start_ms, end_ms)
        log.info(f"fetching {sym_usdc} ...")
        df_usdc = _fetch_klines(sym_usdc, start_ms, end_ms)
        if df_usdt.empty or df_usdc.empty:
            log.warning(f"{base}: empty panel (usdt={len(df_usdt)}, usdc={len(df_usdc)}) -- skip")
            continue
        joined = pd.DataFrame({
            "usdt_close": df_usdt["close"],
            "usdc_close": df_usdc["close"],
            "usdt_quote_vol": df_usdt["quote_vol"],
            "usdc_quote_vol": df_usdc["quote_vol"],
        }).dropna()
        if len(joined) < ROLLING_WINDOW + 50:
            log.warning(f"{base}: only {len(joined)} aligned bars -- skip")
            continue
        panel[base] = joined
        log.info(f"  {base} aligned: {len(joined)} bars from {joined.index[0]} to {joined.index[-1]}")
    return panel


def compute_signal(panel: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    out = {}
    for base, df in panel.items():
        spread = (df["usdc_close"] - df["usdt_close"]) / df["usdt_close"]
        mean = spread.rolling(ROLLING_WINDOW, min_periods=ROLLING_WINDOW // 2).mean()
        std = spread.rolling(ROLLING_WINDOW, min_periods=ROLLING_WINDOW // 2).std(ddof=1)
        z = (spread - mean) / std
        d2 = df.copy()
        d2["spread"] = spread
        d2["spread_z"] = z
        for h in HOLD_SWEEP_BARS:
            d2[f"fwd_{h}"] = d2["usdt_close"].shift(-h) / d2["usdt_close"] - 1.0
        out[base] = d2.dropna(subset=["spread_z"])
    return out


def quadrant_analysis(panel_with_signal: Dict[str, pd.DataFrame], hold_bars: int) -> Dict:
    fwd_col = f"fwd_{hold_bars}"
    quadrants = {
        "A_focus_z_pos_SHORT": {"z_cond": lambda z: z >= Z_THRESHOLD, "direction": -1},
        "A_mirror_z_neg_LONG": {"z_cond": lambda z: z <= -Z_THRESHOLD, "direction": +1},
        "B_same_z_pos_LONG": {"z_cond": lambda z: z >= Z_THRESHOLD, "direction": +1},
        "B_mirror_z_neg_SHORT": {"z_cond": lambda z: z <= -Z_THRESHOLD, "direction": -1},
    }
    result = {}
    candidate_pool_returns = []
    for base, df in panel_with_signal.items():
        for r in df[fwd_col].dropna().values:
            candidate_pool_returns.append(r)
            candidate_pool_returns.append(-r)

    for q_name, q_spec in quadrants.items():
        per_sym_trades = {}
        all_trades = []
        all_dates = []
        for base, df in panel_with_signal.items():
            mask = q_spec["z_cond"](df["spread_z"]) & df[fwd_col].notna()
            entries = df.loc[mask]
            if entries.empty:
                continue
            direction = q_spec["direction"]
            net = direction * entries[fwd_col].values - FEE_RT
            per_sym_trades[base] = net
            all_trades.extend(net.tolist())
            all_dates.extend(entries.index.tolist())
        if len(all_trades) < 30:
            result[q_name] = {
                "n": len(all_trades),
                "error": "n<30 insufficient sample (Lesson #11)",
            }
            continue
        obs = np.array(all_trades)
        fee_perm = fee_aware_perm_test(
            observed_net_returns=obs,
            candidate_pool_returns=candidate_pool_returns,
            fee_per_trade=FEE_RT,
            n_perms=1000,
        )
        ci = bootstrap_ci(obs, n_boot=2000, block_size=1)
        per_sym_ci = {}
        for sym, arr in per_sym_trades.items():
            if len(arr) < 10:
                continue
            sym_ci = bootstrap_ci(arr, n_boot=1000, block_size=1)
            per_sym_ci[sym] = {
                "n": int(len(arr)),
                "mean_bp": float(arr.mean() * 1e4),
                "ci_lower_bp": float(sym_ci["ci_lower"] * 1e4) if not np.isnan(sym_ci["ci_lower"]) else None,
                "ci_pos": bool(sym_ci["ci_lower"] > 0) if not np.isnan(sym_ci["ci_lower"]) else False,
            }
        n_sym_measurable = len(per_sym_ci)
        n_sym_ci_pos = sum(1 for v in per_sym_ci.values() if v["ci_pos"])

        per_q = {}
        per_era = {}
        if all_dates:
            sdf = pd.DataFrame({"date": all_dates, "ret": all_trades}).set_index("date")
            sdf["q"] = sdf.index.to_period("Q").astype(str)
            for q, g in sdf.groupby("q"):
                if len(g) < 10:
                    continue
                arr_q = g["ret"].values
                t_q = float(arr_q.mean() / arr_q.std(ddof=1) * np.sqrt(len(arr_q))) if arr_q.std(ddof=1) > 0 else 0.0
                per_q[q] = {
                    "n": int(len(g)),
                    "mean_bp": float(arr_q.mean() * 1e4),
                    "t": t_q,
                    "pos_t": bool(t_q > 0),
                }
            sdf["era"] = sdf.index.year.astype(str)
            for era, g in sdf.groupby("era"):
                if len(g) < 10:
                    continue
                arr_e = g["ret"].values
                t_e = float(arr_e.mean() / arr_e.std(ddof=1) * np.sqrt(len(arr_e))) if arr_e.std(ddof=1) > 0 else 0.0
                per_era[era] = {
                    "n": int(len(g)),
                    "mean_bp": float(arr_e.mean() * 1e4),
                    "t": t_e,
                }
        n_q_measurable = len(per_q)
        n_q_pos_t = sum(1 for v in per_q.values() if v["pos_t"])

        sig_t_excess = fee_perm.get("signal_t_excess")
        perm_p = fee_perm.get("perm_p_two_sided")
        ci_lower = ci.get("ci_lower")
        ci_upper = ci.get("ci_upper")
        three_gate = bool(
            (sig_t_excess is not None and not np.isnan(sig_t_excess) and sig_t_excess >= 2.0)
            and (ci_lower is not None and not np.isnan(ci_lower) and ci_lower > 0)
            and (perm_p is not None and not np.isnan(perm_p) and perm_p <= 0.10)
        )

        result[q_name] = {
            "n": int(len(obs)),
            "obs_mean_bp": float(obs.mean() * 1e4),
            "obs_t": float(fee_perm["obs_t"]),
            "null_mean_t": None if (fee_perm["null_mean_t"] is None or np.isnan(fee_perm["null_mean_t"])) else float(fee_perm["null_mean_t"]),
            "signal_t_excess": None if (sig_t_excess is None or np.isnan(sig_t_excess)) else float(sig_t_excess),
            "perm_p_two_sided": None if (perm_p is None or np.isnan(perm_p)) else float(perm_p),
            "ci_lower_bp": None if (ci_lower is None or np.isnan(ci_lower)) else float(ci_lower * 1e4),
            "ci_upper_bp": None if (ci_upper is None or np.isnan(ci_upper)) else float(ci_upper * 1e4),
            "prob_positive": None if np.isnan(ci.get("prob_positive", float("nan"))) else float(ci["prob_positive"]),
            "concentration_per_sym": per_sym_ci,
            "concentration_per_quarter": per_q,
            "n_sym_measurable": n_sym_measurable,
            "n_sym_ci_pos": n_sym_ci_pos,
            "sym_ci_pos_ratio": float(n_sym_ci_pos / n_sym_measurable) if n_sym_measurable > 0 else 0.0,
            "n_q_measurable": n_q_measurable,
            "n_q_pos_t": n_q_pos_t,
            "q_pos_t_ratio": float(n_q_pos_t / n_q_measurable) if n_q_measurable > 0 else 0.0,
            "era_stratify": per_era,
            "three_gate_pass": three_gate,
        }
    return result


def unconditional_baseline(panel_with_signal: Dict[str, pd.DataFrame], hold_bars: int) -> Dict:
    fwd_col = f"fwd_{hold_bars}"
    all_returns = []
    for base, df in panel_with_signal.items():
        all_returns.extend(df[fwd_col].dropna().values.tolist())
    if not all_returns:
        return {"error": "empty"}
    arr = np.array(all_returns)
    return {
        "n": int(len(arr)),
        "abs_mean_bp": float(np.abs(arr).mean() * 1e4),
        "long_gross_mean_bp": float(arr.mean() * 1e4),
        "long_net_mean_bp": float((arr.mean() - FEE_RT) * 1e4),
        "short_gross_mean_bp": float(-arr.mean() * 1e4),
        "short_net_mean_bp": float((-arr.mean() - FEE_RT) * 1e4),
        "t_long_gross": float(arr.mean() / arr.std(ddof=1) * np.sqrt(len(arr))) if arr.std(ddof=1) > 0 else 0.0,
    }


def main():
    log.info("=" * 80)
    log.info(f"paradigm 210 R-1 — {PARADIGM_NAME}")
    log.info("=" * 80)

    log.info("Step 1: Fetching paired USDC/USDT panel ...")
    panel = load_paired_panel()
    log.info(f"Loaded {len(panel)} symbols: {list(panel.keys())}")

    if len(panel) < 5:
        log.error(f"Insufficient symbols loaded ({len(panel)} < 5). Halting.")
        return 1

    log.info("Step 2: Computing spread z-score signal + forward returns ...")
    panel_sig = compute_signal(panel)
    trigger_counts = {}
    for base, df in panel_sig.items():
        n_pos = int((df["spread_z"] >= Z_THRESHOLD).sum())
        n_neg = int((df["spread_z"] <= -Z_THRESHOLD).sum())
        trigger_counts[base] = {"n_pos": n_pos, "n_neg": n_neg, "n_bars": int(len(df))}
        log.info(f"  {base}: bars={len(df)} | z>=+2 n={n_pos} | z<=-2 n={n_neg}")

    log.info("Step 3: Primary hold 4h 4-quadrant SNT ...")
    primary = quadrant_analysis(panel_sig, hold_bars=PRIMARY_HOLD)
    for q, r in primary.items():
        if "error" in r:
            log.info(f"  {q}: ERR n={r.get('n', 0)} {r.get('error')}")
        else:
            log.info(
                f"  {q}: n={r['n']} obs_mean={r['obs_mean_bp']:+.2f}bp t={r['obs_t']:+.2f} "
                f"sig_t_ex={_fmt(r['signal_t_excess'])} "
                f"ci_low={_fmt(r['ci_lower_bp'])} "
                f"perm_p={_fmt(r['perm_p_two_sided'], '.3f')} 3gate={r['three_gate_pass']}"
            )

    log.info("Step 4: Hold sweep (1/2/3/6 bars = 4h/8h/12h/24h) ...")
    hold_sweep = {}
    for h in HOLD_SWEEP_BARS:
        log.info(f"  hold {h} bars ({h*4}h) ...")
        hold_sweep[f"hold_{h}_bars_{h*4}h"] = quadrant_analysis(panel_sig, hold_bars=h)

    log.info("Step 5: Unconditional baseline (Lesson #39) ...")
    unc = unconditional_baseline(panel_sig, hold_bars=PRIMARY_HOLD)
    log.info(f"  unconditional: abs_mean={unc.get('abs_mean_bp', 0):.2f}bp, long_gross={unc.get('long_gross_mean_bp', 0):+.2f}bp, t_long={unc.get('t_long_gross', 0):+.2f}")

    cross_set_asym = {}
    if "A_focus_z_pos_SHORT" in primary and "error" not in primary["A_focus_z_pos_SHORT"]:
        focus_mag = abs(primary["A_focus_z_pos_SHORT"].get("obs_mean_bp", 0))
        mirror_mag = abs(primary.get("A_mirror_z_neg_LONG", {}).get("obs_mean_bp", 0))
        ratio = focus_mag / mirror_mag if mirror_mag > 0 else float("inf")
        cross_set_asym = {
            "focus_abs_mean_bp": focus_mag,
            "mirror_abs_mean_bp": mirror_mag,
            "asymmetry_ratio": ratio,
            "unc_abs_mean_bp": unc.get("abs_mean_bp", 0),
        }

    metrics = {
        "paradigm_name": PARADIGM_NAME,
        "phase": "R-1",
        "config": {
            "universe": UNIVERSE_BASE,
            "interval": INTERVAL,
            "start_date": START_DATE.isoformat(),
            "end_date": END_DATE.isoformat(),
            "rolling_window_bars": ROLLING_WINDOW,
            "z_threshold": Z_THRESHOLD,
            "fee_rt": FEE_RT,
            "primary_hold_bars": PRIMARY_HOLD,
        },
        "trigger_counts": trigger_counts,
        "primary_hold_4h": primary,
        "hold_sweep": hold_sweep,
        "unconditional_baseline": unc,
        "cross_set_asymmetry": cross_set_asym,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }

    out_path = OUTPUT_DIR / "r1__metrics.json"
    with open(out_path, "w") as f:
        json.dump(metrics, f, indent=2, default=str)
    log.info(f"Wrote metrics: {out_path}")

    log.info("=" * 80)
    log.info("PRIMARY HOLD 4h 4-QUADRANT VERDICT:")
    for q, r in primary.items():
        if "error" in r:
            log.info(f"  {q}: ERR")
        else:
            log.info(f"  {q}: 3gate={'PASS' if r['three_gate_pass'] else 'FAIL'}")

    sweep_passes = []
    for h_key, h_result in hold_sweep.items():
        for q, r in h_result.items():
            if r.get("three_gate_pass"):
                sweep_passes.append(f"{h_key}::{q}")
    log.info(f"Hold-sweep 3gate PASS cells: {sweep_passes if sweep_passes else 'NONE'}")
    log.info("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())
