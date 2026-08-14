"""paradigm-architect R-1 PoC — btc_spot_etf_netflow_regime_weekly_bilateral

Thesis:
  Since spot BTC ETF approval (2024-01-11), authorized participants must
  create/redeem shares by buying/selling BTC spot. Aggregate daily net flow
  is therefore a proxy for institutional demand cycles. Extreme rolling
  5-day cumulative net flow (top/bottom percentile of 90-day window)
  predicts biased BTCUSDT perp forward returns over 14 days.

Substrate:
  SoSoValue openapi /openapi/v2/etf/historicalInflowChart (type=us-btc-spot).
  Public, no auth required. Cap ~300 daily rows (~14 months window).

Design:
  - Signal = 90d rolling percentile rank of 5d cumulative netInflow.
  - LONG when rank ≥ 0.80, SHORT when rank ≤ 0.20. One trade active max.
  - Entry: T+1 daily close (BTCUSDT 1m data at 23:59 UTC of entry day).
  - Exit: entry_ts + 14 calendar days at daily close.
  - Fee: 0.04% per leg × 2 = 0.0008 round-trip.
  - Also produce a T+2 delayed variant to feed G2 edge_after_1bar.

Output:
  runs/research_track/btc_spot_etf_netflow_regime_weekly_bilateral/
    r1_trades.json          — [{entry_ts, exit_ts, net_ret, side, rank}]
    r1_trades_delayed.json  — same, but entry at T+2 (for G2 delay measurement)
    r1_metrics.json         — {n_trades, win_rate, mean_net_ret, sharpe, ...}
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("etf_netflow_r1")

OUT_DIR = ROOT / "runs" / "research_track" / "btc_spot_etf_netflow_regime_weekly_bilateral"
CACHE_1M = ROOT / "runs" / "ohlcv_cache" / "BTCUSDT_1m.joblib"

FEE_ROUNDTRIP = 0.0008   # 0.04% × 2 legs
ROLL_CUM = 5             # 5-day rolling cumulative flow
PCTL_WIN = 90            # 90-day rolling window for percentile rank
LONG_RANK = 0.80
SHORT_RANK = 0.20
HOLD_DAYS = 14


def fetch_etf_flow() -> pd.DataFrame:
    """SoSoValue historical inflow — 300 daily rows max, no auth."""
    r = requests.post(
        "https://api.sosovalue.xyz/openapi/v2/etf/historicalInflowChart",
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
        json={"type": "us-btc-spot"},
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"SoSoValue error: {payload}")
    df = pd.DataFrame(payload["data"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df["totalNetInflow"] = pd.to_numeric(df["totalNetInflow"], errors="coerce")
    return df[["date", "totalNetInflow"]]


def load_btc_1m() -> pd.DataFrame:
    """Merge joblib cache (older) + DB (newer) into one 1m DataFrame."""
    import joblib
    from sqlalchemy import text as sql_text

    parts = []
    if CACHE_1M.exists():
        cached = joblib.load(CACHE_1M)
        parts.append(cached)
        log.info("cache: %d rows %s → %s", len(cached), cached.index.min(), cached.index.max())

    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        rows = db.execute(
            sql_text(
                "SELECT timestamp, open, high, low, close, volume FROM ohlcv "
                "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
            ),
            {"s": "BTCUSDT"},
        ).fetchall()
    finally:
        db.close()

    if rows:
        db_df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        db_df["timestamp"] = pd.to_datetime(db_df["timestamp"])
        db_df = db_df.set_index("timestamp").sort_index()
        for c in ("open", "high", "low", "close", "volume"):
            db_df[c] = pd.to_numeric(db_df[c], errors="coerce")
        db_df = db_df[~db_df.index.duplicated(keep="first")]
        parts.append(db_df)
        log.info("db:    %d rows %s → %s", len(db_df), db_df.index.min(), db_df.index.max())

    if not parts:
        raise RuntimeError("no OHLCV data available")

    merged = pd.concat(parts).sort_index()
    merged = merged[~merged.index.duplicated(keep="first")]
    log.info("merged: %d rows %s → %s", len(merged), merged.index.min(), merged.index.max())
    return merged


def daily_close_at(btc_1m: pd.DataFrame, day: pd.Timestamp) -> float | None:
    """Return the last close price on `day` UTC. None if no data."""
    slot = btc_1m.loc[
        (btc_1m.index.date == day.date())
    ]
    if slot.empty:
        return None
    return float(slot["close"].iloc[-1])


def build_signals(flow_df: pd.DataFrame) -> pd.DataFrame:
    """Compute rolling 5d cum flow + 90d percentile rank + side."""
    df = flow_df.copy()
    df["cum5"] = df["totalNetInflow"].rolling(ROLL_CUM, min_periods=ROLL_CUM).sum()
    df["rank90"] = df["cum5"].rolling(PCTL_WIN, min_periods=30).rank(pct=True)
    df["side"] = "none"
    df.loc[df["rank90"] >= LONG_RANK, "side"] = "long"
    df.loc[df["rank90"] <= SHORT_RANK, "side"] = "short"
    return df


def run_backtest(sig_df: pd.DataFrame, btc_1m: pd.DataFrame,
                 entry_offset_days: int = 1) -> tuple[list[dict], list[str]]:
    """Generate non-overlapping trades. entry_offset_days=1 for T+1 (standard),
    =2 for T+2 (G2 delay probe)."""
    trades: list[dict] = []
    skipped: list[str] = []
    cursor: pd.Timestamp | None = None  # end of most recent active trade

    for _, row in sig_df.iterrows():
        side = row["side"]
        if side == "none":
            continue
        signal_day = pd.Timestamp(row["date"]).normalize()
        entry_day = signal_day + pd.Timedelta(days=entry_offset_days)
        exit_day = entry_day + pd.Timedelta(days=HOLD_DAYS)

        if cursor is not None and entry_day <= cursor:
            continue  # already in a trade

        entry_px = daily_close_at(btc_1m, entry_day)
        exit_px = daily_close_at(btc_1m, exit_day)
        if entry_px is None or exit_px is None:
            skipped.append(f"{signal_day.date()} {side} — no px "
                           f"(entry={entry_px} exit={exit_px})")
            continue

        gross = (exit_px - entry_px) / entry_px
        if side == "short":
            gross = -gross
        net = gross - FEE_ROUNDTRIP

        trades.append({
            "signal_ts": signal_day.isoformat(),
            "entry_ts": entry_day.isoformat(),
            "exit_ts": exit_day.isoformat(),
            "side": side,
            "rank90": round(float(row["rank90"]), 4),
            "cum5_flow_musd": round(float(row["cum5"]) / 1e6, 2),
            "entry_px": entry_px,
            "exit_px": exit_px,
            "gross_ret": round(gross, 6),
            "net_ret": round(net, 6),
        })
        cursor = exit_day

    return trades, skipped


def summarize(trades: list[dict], label: str) -> dict:
    if not trades:
        return {"label": label, "n_trades": 0}
    net = np.array([t["net_ret"] for t in trades])
    long_mask = np.array([t["side"] == "long" for t in trades])
    short_mask = ~long_mask
    ann = np.sqrt(365.0 / HOLD_DAYS)  # 26 non-overlap trades/yr max
    sharpe = float(net.mean() / net.std(ddof=1) * ann) if net.std(ddof=1) > 0 else float("nan")

    return {
        "label": label,
        "n_trades": int(len(trades)),
        "n_long": int(long_mask.sum()),
        "n_short": int(short_mask.sum()),
        "win_rate": round(float((net > 0).mean()), 4),
        "mean_net_ret": round(float(net.mean()), 6),
        "median_net_ret": round(float(np.median(net)), 6),
        "std_net_ret": round(float(net.std(ddof=1)), 6),
        "sharpe_annualized": round(sharpe, 3),
        "sum_net_ret": round(float(net.sum()), 6),
        "long_edge": round(float(net[long_mask].mean()), 6) if long_mask.any() else None,
        "short_edge": round(float(net[short_mask].mean()), 6) if short_mask.any() else None,
        "first_signal": trades[0]["signal_ts"],
        "last_signal": trades[-1]["signal_ts"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("stage 1/4: fetch ETF flow")
    flow = fetch_etf_flow()
    log.info("  %d rows, %s → %s", len(flow), flow["date"].min().date(), flow["date"].max().date())

    log.info("stage 2/4: load BTC 1m OHLCV")
    btc = load_btc_1m()

    log.info("stage 3/4: build signals")
    sig = build_signals(flow)
    n_sig = int((sig["side"] != "none").sum())
    log.info("  raw signals: %d long + %d short = %d",
             int((sig["side"] == "long").sum()),
             int((sig["side"] == "short").sum()),
             n_sig)
    sig[["date", "totalNetInflow", "cum5", "rank90", "side"]].to_csv(
        out_dir / "r1_signals_debug.csv", index=False)

    log.info("stage 4/4: backtest (T+1 standard + T+2 delayed)")
    trades_t1, skipped_t1 = run_backtest(sig, btc, entry_offset_days=1)
    trades_t2, skipped_t2 = run_backtest(sig, btc, entry_offset_days=2)

    log.info("  T+1: %d trades, %d skipped", len(trades_t1), len(skipped_t1))
    log.info("  T+2: %d trades, %d skipped", len(trades_t2), len(skipped_t2))

    # Persist trades in the schema tier3_gate expects
    def _dump(rows: list[dict], path: Path) -> None:
        with open(path, "w") as f:
            json.dump([{"entry_ts": r["entry_ts"], "exit_ts": r["exit_ts"],
                        "net_ret": r["net_ret"], "side": r["side"]} for r in rows], f, indent=2)

    _dump(trades_t1, out_dir / "r1_trades.json")
    _dump(trades_t2, out_dir / "r1_trades_delayed.json")

    with open(out_dir / "r1_trades_full.json", "w") as f:
        json.dump(trades_t1, f, indent=2)

    metrics = {
        "t1_standard": summarize(trades_t1, "T+1 standard"),
        "t2_delayed":  summarize(trades_t2, "T+2 delayed"),
        "skipped_t1_examples": skipped_t1[:5],
        "skipped_t2_examples": skipped_t2[:5],
        "config": {
            "roll_cum_days": ROLL_CUM,
            "pctl_win_days": PCTL_WIN,
            "long_rank_threshold": LONG_RANK,
            "short_rank_threshold": SHORT_RANK,
            "hold_days": HOLD_DAYS,
            "fee_roundtrip": FEE_ROUNDTRIP,
        },
        "data_spans": {
            "etf_flow_first": flow["date"].min().isoformat(),
            "etf_flow_last": flow["date"].max().isoformat(),
            "etf_flow_rows": int(len(flow)),
            "btc_1m_first": btc.index.min().isoformat(),
            "btc_1m_last": btc.index.max().isoformat(),
            "btc_1m_rows": int(len(btc)),
        },
    }
    with open(out_dir / "r1_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    log.info("─" * 60)
    log.info("T+1 summary: %s", json.dumps(metrics["t1_standard"], indent=None))
    log.info("T+2 summary: %s", json.dumps(metrics["t2_delayed"], indent=None))
    log.info("outputs → %s", out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
