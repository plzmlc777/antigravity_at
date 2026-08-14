"""Paradigm 251 R-1 — alt_stablecoin_supply_net_flow_7d_z_bilateral_alt_1d_3d.

Hypothesis: Net 7-day USDT+USDC stablecoin market cap change (z-scored over 60d
rolling window) as crypto capital inflow signal.
  z > +1.0 → LONG alt perps (new capital entering crypto)
  z < -1.0 → SHORT alt perps (redemptions, capital leaving)

Substrate: CoinGecko public API (non-OHLCV, external market cap).
Signal: daily, entry T+1 open, exit T+1+hold close. Hold sweep 1d/2d/3d.
Fee: 0.04% per leg × 2 = 0.0008 round-trip (8 bp).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "runs" / "research_track" / "paradigm_251_stablecoin_supply_flow"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OHLCV_CACHE = ROOT / "runs" / "ohlcv_cache"

FEE_RT = 0.0008
Z_THRESH = 1.0
ROLL_WIN = 60
NET_DAYS = 7
HOLDS = [1, 2, 3]
UNIVERSE = ["SOLUSDT", "AVAXUSDT", "DOGEUSDT", "LINKUSDT", "XRPUSDT", "BNBUSDT"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("p251")


def fetch_mcap_history(coin_id: str, retries: int = 6) -> pd.DataFrame:
    """CoinGecko market_chart — free tier: 365 days daily. Retry on 429 with backoff."""
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    delay = 5.0
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.get(
                url,
                params={"vs_currency": "usd", "days": 365},
                timeout=30,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if r.status_code == 429:
                log.warning(f"  429 on {coin_id} attempt {attempt+1} — sleep {delay:.0f}s")
                time.sleep(delay)
                delay = min(delay * 2, 120.0)
                continue
            r.raise_for_status()
            data = r.json()
            df = pd.DataFrame(data["market_caps"], columns=["ts_ms", "mcap"])
            df["date"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True).dt.normalize()
            df = df.groupby("date", as_index=False)["mcap"].last()
            return df.sort_values("date").reset_index(drop=True)
        except requests.HTTPError as e:
            last_err = e
            log.warning(f"  HTTP error on {coin_id} attempt {attempt+1}: {e}")
            time.sleep(delay)
            delay = min(delay * 2, 120.0)
    raise RuntimeError(f"CoinGecko fetch failed for {coin_id} after {retries} retries: {last_err}")


def build_signal() -> pd.DataFrame:
    """Build daily stablecoin supply z-score signal."""
    cache_path = OUT_DIR / "stablecoin_supply_cache.json"
    if cache_path.exists():
        log.info("Loading cached stablecoin supply data")
        raw = json.loads(cache_path.read_text())
        usdt = pd.DataFrame(raw["usdt"])
        usdc = pd.DataFrame(raw["usdc"])
        usdt["date"] = pd.to_datetime(usdt["date"], utc=True)
        usdc["date"] = pd.to_datetime(usdc["date"], utc=True)
    else:
        log.info("Fetching USDT market cap from CoinGecko...")
        usdt = fetch_mcap_history("tether")
        time.sleep(15.0)  # generous spacing for public tier
        log.info("Fetching USDC market cap from CoinGecko...")
        usdc = fetch_mcap_history("usd-coin")
        cache_path.write_text(
            json.dumps(
                {
                    "usdt": [
                        {"date": d.isoformat(), "mcap": float(m)}
                        for d, m in zip(usdt["date"], usdt["mcap"])
                    ],
                    "usdc": [
                        {"date": d.isoformat(), "mcap": float(m)}
                        for d, m in zip(usdc["date"], usdc["mcap"])
                    ],
                }
            )
        )
        log.info(f"Cached to {cache_path}")

    df = usdt.merge(usdc, on="date", suffixes=("_usdt", "_usdc"))
    df["combined_supply"] = df["mcap_usdt"] + df["mcap_usdc"]
    df = df.sort_values("date").reset_index(drop=True)
    df["net_7d"] = df["combined_supply"].diff(NET_DAYS)
    df["z"] = (
        df["net_7d"] - df["net_7d"].rolling(ROLL_WIN).mean()
    ) / df["net_7d"].rolling(ROLL_WIN).std()
    return df[["date", "combined_supply", "net_7d", "z"]].dropna().reset_index(drop=True)


def load_daily_ohlcv(sym: str) -> pd.DataFrame:
    cache_f = OHLCV_CACHE / f"{sym}_1m.joblib"
    if not cache_f.exists():
        raise FileNotFoundError(f"OHLCV cache not found: {cache_f}")
    df = joblib.load(cache_f)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    daily = df.resample("1D").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()
    daily.index = daily.index.normalize()
    return daily


def backtest(sym: str, signal_df: pd.DataFrame, entry_lag_days: int = 1) -> dict:
    try:
        price = load_daily_ohlcv(sym)
    except Exception as e:
        log.warning(f"{sym}: failed to load OHLCV — {e}")
        return {}
    price = price.copy()
    price["date_d"] = price.index.date
    price_by_date = {d: (o, c) for d, o, c in zip(price["date_d"], price["open"], price["close"])}

    results = {}
    for hold in HOLDS:
        trades = []
        for _, row in signal_df.iterrows():
            z = row["z"]
            if abs(z) < Z_THRESH:
                continue
            side = "long" if z > 0 else "short"
            sig_date = row["date"].date()
            entry_d = sig_date + timedelta(days=entry_lag_days)
            exit_d = entry_d + timedelta(days=hold)
            e_row = price_by_date.get(entry_d)
            x_row = price_by_date.get(exit_d)
            if e_row is None or x_row is None:
                continue
            entry_px = float(e_row[0])
            exit_px = float(x_row[1])
            if not np.isfinite(entry_px) or not np.isfinite(exit_px) or entry_px <= 0:
                continue
            gross = (exit_px - entry_px) / entry_px if side == "long" else (entry_px - exit_px) / entry_px
            net = gross - FEE_RT
            entry_ts = datetime.combine(entry_d, datetime.min.time()).replace(tzinfo=timezone.utc)
            exit_ts = datetime.combine(exit_d, datetime.min.time()).replace(tzinfo=timezone.utc)
            trades.append({
                "entry_ts": entry_ts.isoformat(),
                "exit_ts": exit_ts.isoformat(),
                "net_ret": net,
                "side": side,
                "z": float(z),
                "sym": sym,
                "hold": hold,
            })
        results[f"h{hold}d"] = trades
    return results


def summarize_cell(trades: list) -> dict:
    if not trades:
        return {"n": 0}
    nets = np.array([t["net_ret"] for t in trades], dtype=float)
    n = int(len(nets))
    mean = float(np.mean(nets))
    std = float(np.std(nets, ddof=1)) if n > 1 else 0.0
    t_stat = float(mean / (std / np.sqrt(n))) if std > 0 and n > 1 else 0.0
    win = float(np.mean(nets > 0))
    return {"n": n, "mean_ret": mean, "std": std, "t_stat": t_stat, "win_rate": win}


def main():
    log.info("=== Paradigm 251 R-1: stablecoin supply flow bilateral ===")
    signal_df = build_signal()
    n_trig = int((signal_df["z"].abs() >= Z_THRESH).sum())
    n_long = int((signal_df["z"] >= Z_THRESH).sum())
    n_short = int((signal_df["z"] <= -Z_THRESH).sum())
    log.info(
        f"Signal: {len(signal_df)} days | triggers |z|>={Z_THRESH}: {n_trig} "
        f"(long={n_long}, short={n_short})"
    )
    if len(signal_df) < 120:
        log.error(f"DATA_INSUFFICIENT: signal_df has only {len(signal_df)} rows")
        (OUT_DIR / "r1_summary.json").write_text(
            json.dumps({"verdict": "DATA_INSUFFICIENT_COINGECKO_API", "n": len(signal_df)}, indent=2)
        )
        return

    # Lesson #79 predictive content pretest — signed direction is what matters
    pretest = {}
    try:
        sol = load_daily_ohlcv("SOLUSDT")
        sol_fwd_1d = sol["close"].pct_change().shift(-1)
        merged = signal_df.set_index("date").join(sol_fwd_1d.rename("fwd_ret"), how="inner")
        corr_full = float(merged["z"].corr(merged["fwd_ret"]))
        trig_mask = merged["z"].abs() >= Z_THRESH
        n_trig_ov = int(trig_mask.sum())
        if n_trig_ov > 0:
            signed_exp = float((np.sign(merged.loc[trig_mask, "z"]) * merged.loc[trig_mask, "fwd_ret"]).mean())
        else:
            signed_exp = 0.0
        pretest = {"corr_z_fwd1d_SOL": corr_full, "signed_exp_fwd1d_SOL": signed_exp, "n_trig_overlap": n_trig_ov}
        log.info(
            f"LESSON79 PRETEST: corr(z,fwd1d_SOL)={corr_full:+.4f} "
            f"E[sign(z)*fwd1d]={signed_exp:+.5f} on n_overlap={n_trig_ov}"
        )
    except Exception as e:
        log.warning(f"Pretest failed: {e}")

    # Standard T+1
    all_summaries = {}
    for sym in UNIVERSE:
        log.info(f"Backtesting {sym} (T+1 entry)...")
        by_hold = backtest(sym, signal_df, entry_lag_days=1)
        for hold_key, trades in by_hold.items():
            path = OUT_DIR / f"r1_trades_{sym}_{hold_key}.json"
            path.write_text(json.dumps(trades, indent=2))
            s = summarize_cell(trades)
            all_summaries[f"{sym}_{hold_key}"] = s
            log.info(
                f"  {sym} {hold_key}: n={s['n']} "
                f"mean={s.get('mean_ret',0)*100:+.3f}% t={s.get('t_stat',0):+.2f} "
                f"win={s.get('win_rate',0)*100:.1f}%"
            )

    # T+2 delayed for G2
    delayed_summaries = {}
    for sym in UNIVERSE:
        by_hold = backtest(sym, signal_df, entry_lag_days=2)
        for hold_key, trades in by_hold.items():
            path = OUT_DIR / f"r1_trades_delayed_{sym}_{hold_key}.json"
            path.write_text(json.dumps(trades, indent=2))
            s = summarize_cell(trades)
            delayed_summaries[f"{sym}_{hold_key}"] = s

    summary = {
        "paradigm": "alt_stablecoin_supply_net_flow_7d_z_bilateral_alt_1d_3d",
        "universe": UNIVERSE,
        "z_thresh": Z_THRESH,
        "roll_win": ROLL_WIN,
        "net_days": NET_DAYS,
        "holds": HOLDS,
        "fee_rt": FEE_RT,
        "signal_days": int(len(signal_df)),
        "triggers_total": n_trig,
        "triggers_long": n_long,
        "triggers_short": n_short,
        "lesson79_pretest": pretest,
        "cells": all_summaries,
        "cells_delayed_1bar": delayed_summaries,
    }
    (OUT_DIR / "r1_summary.json").write_text(json.dumps(summary, indent=2))
    log.info(f"Done. Results in {OUT_DIR}")


if __name__ == "__main__":
    main()
