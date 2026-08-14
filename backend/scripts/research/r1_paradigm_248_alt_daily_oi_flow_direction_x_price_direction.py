"""Paradigm 248 R-1 backtest — alt daily OI flow direction × price direction coupling.

Hypothesis: OI_delta_z aligned with price return direction signals new position
accumulation → 1-3d continuation. Distinct from p21 (OI_up × price_DOWN squeeze).

Universe: 7 alt USDT-M perps with hourly OI cached (AVAX/BCH/BNB/DOGE/LINK/SOL/XRP).
BTC/ETH excluded per hypothesis (too efficient).

Trigger threshold: |OI_delta_z| >= 1.0 AND |daily_ret| >= 0.5%.

Quadrants:
  A-focus:  OI+ & ret+  → LONG   (new longs piling in)
  A-mirror: OI+ & ret+  → SHORT  (mirror check)
  B-focus:  OI- & ret-  → SHORT  (new shorts + falling)
  B-mirror: OI- & ret+  → LONG   (this is p21 squeeze mechanism)

Hold sweep: 1d, 2d, 3d. Entry at T+1 daily open (no lookahead). Exit at T+1+hold close.
Fee: 0.04% each side, so net_ret = gross - 0.0008.
"""
from __future__ import annotations

import json
import logging
from datetime import timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("p248_r1")

ROOT = Path("/home/mint/auto_trading/backend")
CACHE = ROOT / "runs" / "ohlcv_cache"
OUT_DIR = ROOT / "runs" / "research_track" / "248_alt_daily_oi_flow_direction_x_price_direction"
OUT_DIR.mkdir(parents=True, exist_ok=True)

UNIVERSE = ["AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT", "LINKUSDT", "SOLUSDT", "XRPUSDT"]

Z_THRESH = 1.0
RET_THRESH = 0.005        # 0.5% daily return threshold
ROLLING_WINDOW = 60       # 60-day baseline for z-score
FEE_ROUNDTRIP = 0.0008    # 0.04% each side = 0.08% roundtrip
HOLDS = [1, 2, 3]         # days

QUADRANTS = {
    "A_focus":  {"oi_dir": "+", "ret_dir": "+", "side": "long"},
    "A_mirror": {"oi_dir": "+", "ret_dir": "+", "side": "short"},
    "B_focus":  {"oi_dir": "-", "ret_dir": "-", "side": "short"},
    "B_mirror": {"oi_dir": "-", "ret_dir": "+", "side": "long"},
}


def load_daily(sym: str) -> pd.DataFrame:
    """OI + OHLCV → daily frame.

    Lookahead invariant: signal at T uses only data up to end of day T (OI + close).
    Entry at T+1 open. Exit at T+1+hold close.
    """
    oi = joblib.load(CACHE / "binance_oi" / f"{sym}_1h.joblib")
    oi['ts'] = pd.to_datetime(oi['ts'])
    oi = oi.set_index('ts').sort_index()
    oi_daily = oi['oi'].resample('1D').last().dropna()

    ohlcv = joblib.load(CACHE / f"{sym}_1m.joblib")
    ohlcv = ohlcv.sort_index()
    open_daily = ohlcv['open'].resample('1D').first().dropna()
    close_daily = ohlcv['close'].resample('1D').last().dropna()

    df = pd.concat(
        [oi_daily.rename('oi'),
         open_daily.rename('open'),
         close_daily.rename('close')], axis=1
    ).dropna()
    df['oi_delta'] = df['oi'].diff()
    df['ret'] = df['close'].pct_change()
    m = df['oi_delta'].rolling(ROLLING_WINDOW).mean()
    s = df['oi_delta'].rolling(ROLLING_WINDOW).std()
    df['oi_delta_z'] = (df['oi_delta'] - m) / s
    return df.dropna(subset=['oi_delta_z', 'ret'])


def match_quadrant(row, oi_dir: str, ret_dir: str) -> bool:
    z, r = row['oi_delta_z'], row['ret']
    if oi_dir == "+" and z < Z_THRESH: return False
    if oi_dir == "-" and z > -Z_THRESH: return False
    if ret_dir == "+" and r < RET_THRESH: return False
    if ret_dir == "-" and r > -RET_THRESH: return False
    return True


def run_backtest(df: pd.DataFrame, quadrant_key: str, hold_days: int) -> list:
    """Vectorized-ish backtest. Signal at T → entry T+1 open → exit T+1+hold close."""
    cfg = QUADRANTS[quadrant_key]
    trades = []
    idx = df.index
    for i in range(len(df) - hold_days - 1):
        row = df.iloc[i]
        if not match_quadrant(row, cfg["oi_dir"], cfg["ret_dir"]):
            continue
        entry_ts = idx[i + 1]
        exit_idx = i + 1 + hold_days
        if exit_idx >= len(df):
            break
        exit_ts = idx[exit_idx]
        entry_px = df.iloc[i + 1]['open']
        exit_px = df.iloc[exit_idx]['close']
        gross_ret = (exit_px / entry_px) - 1.0
        if cfg["side"] == "short":
            gross_ret = -gross_ret
        net_ret = gross_ret - FEE_ROUNDTRIP
        trades.append({
            "entry_ts": entry_ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "exit_ts": exit_ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "net_ret": round(float(net_ret), 6),
            "gross_ret": round(float(gross_ret), 6),
        })
    return trades


def compute_edge_after_1bar_delay(df: pd.DataFrame, quadrant_key: str, hold_days: int) -> float:
    """G2 input: mean net_ret with entry at T+2 instead of T+1."""
    cfg = QUADRANTS[quadrant_key]
    rets = []
    idx = df.index
    for i in range(len(df) - hold_days - 2):
        row = df.iloc[i]
        if not match_quadrant(row, cfg["oi_dir"], cfg["ret_dir"]):
            continue
        exit_idx = i + 2 + hold_days
        if exit_idx >= len(df):
            break
        entry_px = df.iloc[i + 2]['open']
        exit_px = df.iloc[exit_idx]['close']
        gross_ret = (exit_px / entry_px) - 1.0
        if cfg["side"] == "short":
            gross_ret = -gross_ret
        rets.append(gross_ret - FEE_ROUNDTRIP)
    return float(np.mean(rets)) if rets else 0.0


def summarize(trades: list) -> dict:
    if not trades:
        return {"n": 0}
    x = np.array([t["net_ret"] for t in trades])
    n = len(x)
    mean = float(x.mean())
    std = float(x.std())
    sharpe = mean / std * np.sqrt(252 / max(1, n / n)) if std > 0 else 0.0  # per-trade sharpe approx
    # actually use per-trade t-stat scaled
    t_stat = mean / (std / np.sqrt(n)) if std > 0 else 0.0
    return {
        "n": n,
        "mean_pct": round(mean * 100, 4),
        "median_pct": round(float(np.median(x)) * 100, 4),
        "std_pct": round(std * 100, 4),
        "t_stat": round(t_stat, 3),
        "sharpe_pertrade": round(sharpe, 3),
        "win_rate": round(float((x > 0).mean()), 3),
    }


def main():
    log.info("R-1 backtest — paradigm 248")
    all_summary = {}
    best = None  # (sharpe, key, hold, sym, summary, trades)

    for sym in UNIVERSE:
        try:
            df = load_daily(sym)
        except Exception as e:
            log.warning(f"{sym} load failed: {e}")
            continue
        log.info(f"{sym}: {len(df)} daily rows, {df.index.min().date()} → {df.index.max().date()}")
        for qkey in QUADRANTS:
            for hold in HOLDS:
                trades = run_backtest(df, qkey, hold)
                summ = summarize(trades)
                summ["symbol"] = sym
                summ["quadrant"] = qkey
                summ["hold_days"] = hold
                key = f"{sym}_{qkey}_{hold}d"
                all_summary[key] = summ

                # persist trades
                out_trades = OUT_DIR / f"r1_trades_{key}.json"
                with open(out_trades, "w") as f:
                    json.dump(trades, f)

                # Pick best by t_stat with N>=20
                if summ["n"] >= 20:
                    score = summ["t_stat"]
                    if best is None or score > best[0]:
                        best = (score, key, summ)

    # Save summary
    with open(OUT_DIR / "r1_summary.json", "w") as f:
        json.dump({
            "config": {
                "z_thresh": Z_THRESH,
                "ret_thresh": RET_THRESH,
                "rolling_window": ROLLING_WINDOW,
                "fee_roundtrip": FEE_ROUNDTRIP,
                "holds": HOLDS,
                "universe": UNIVERSE,
            },
            "cells": all_summary,
            "best": {"key": best[1], "t_stat": best[0], "summary": best[2]} if best else None,
        }, f, indent=2)

    log.info(f"Best cell: {best[1] if best else 'NONE'} (t={best[0] if best else 'nan'})")
    log.info("Top 5 by t_stat (n>=20):")
    ranked = sorted(
        [v for v in all_summary.values() if v["n"] >= 20],
        key=lambda s: s["t_stat"],
        reverse=True
    )[:10]
    for r in ranked:
        log.info(f"  {r['symbol']:<10} {r['quadrant']:<9} h={r['hold_days']}d  "
                 f"n={r['n']:>3}  mean={r['mean_pct']:+.3f}%  t={r['t_stat']:+.2f}  "
                 f"win={r['win_rate']:.2f}")

    # For BEST, compute edge_after_1bar_delay for G2
    if best:
        _, key, summ = best
        sym = summ["symbol"]; qk = summ["quadrant"]; hold = summ["hold_days"]
        df = load_daily(sym)
        edge_delayed = compute_edge_after_1bar_delay(df, qk, hold)
        log.info(f"G2 edge_after_1bar_delay for BEST ({key}): {edge_delayed*100:+.4f}%")
        with open(OUT_DIR / "best_g2_inputs.json", "w") as f:
            json.dump({
                "best_key": key,
                "best_summary": summ,
                "edge_after_1bar_delay": round(edge_delayed, 6),
                "hold_minutes": hold * 1440,
                "cycle_minutes": 1440,
                "friction_roundtrip": FEE_ROUNDTRIP,
            }, f, indent=2)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
