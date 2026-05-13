"""Direction 2 PoC — Funding boundary front-running.

Hypothesis: in the 30 min BEFORE a funding payment (00:00/08:00/16:00 UTC),
the funding payer's unwinding pressure creates a systematic price drift in
the OPPOSITE direction of the funding sign. After the boundary, the move
mean-reverts.

Specifically:
  - funding_rate > 0 (longs pay): expect price drift DOWN pre-boundary,
    bounce UP post-boundary.
  - funding_rate < 0 (shorts pay): expect price drift UP pre-boundary,
    drop DOWN post-boundary.

Test: for each funding event over 1y, compute pre_30m_ret, post_30m_ret,
group by sign(funding_rate). If hypothesis holds, the pre*post correlation
should be NEGATIVE (mean reversion) and stratified by funding sign in a
specific predicted direction.

Significance: t-test of pre-boundary direction vs random walk null + cohort
mean post-boundary return.

Symbols: 14 paper-pool symbols + 2 leaders (BTC, ETH).
Window: events where funding |rate| > 0.0001 (10 bps annualized, filters noise).

Output: backend/runs/research_track/funding_boundary/poc__metrics.json
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("funding_boundary_poc")

SYMBOLS = [
    "BTCUSDT", "ETHUSDT",
    "SOLUSDT", "HBARUSDT", "AXSUSDT", "DOGEUSDT", "UNIUSDT", "PYTHUSDT",
    "TONUSDT", "ICPUSDT", "ETCUSDT", "JUPUSDT", "COMPUSDT", "WLDUSDT",
    "LDOUSDT", "AVAXUSDT", "LINKUSDT",
]

PRE_WINDOW_MIN = 30   # 30 min before funding boundary
POST_WINDOW_MIN = 30  # 30 min after
FUNDING_RATE_MIN_ABS = 0.0001  # 1 bp per 8h ≈ 11% annualized — filter near-zero events
OUT_PATH = ROOT / "runs" / "research_track" / "funding_boundary" / "poc__metrics.json"


def _load_funding(db, sym: str) -> pd.DataFrame:
    rows = db.execute(text(
        "SELECT funding_time, funding_rate FROM binance_funding_rate "
        "WHERE symbol=:s ORDER BY funding_time"
    ), {"s": sym}).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["funding_time", "funding_rate"])
    df["funding_time"] = pd.to_datetime(df["funding_time"]).dt.floor("min")
    df["funding_rate"] = pd.to_numeric(df["funding_rate"], errors="coerce")
    return df.dropna()


def _load_ohlcv_1m(db, sym: str) -> pd.DataFrame:
    rows = db.execute(text(
        "SELECT timestamp, close FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
    ), {"s": sym}).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["timestamp", "close"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df.set_index("timestamp").sort_index().dropna()


def _event_returns(ohlcv: pd.DataFrame, ts: pd.Timestamp):
    """Given a funding event at ts, return (pre_30m_ret, post_30m_ret) or (None,None)."""
    # pre: close at ts-1min vs close at ts-30min
    pre_start = ts - timedelta(minutes=PRE_WINDOW_MIN)
    pre_end = ts - timedelta(minutes=1)
    post_start = ts + timedelta(minutes=1)
    post_end = ts + timedelta(minutes=POST_WINDOW_MIN)

    try:
        p0 = ohlcv.loc[pre_start, "close"]
        p1 = ohlcv.loc[pre_end, "close"]
        p2 = ohlcv.loc[post_start, "close"]
        p3 = ohlcv.loc[post_end, "close"]
    except KeyError:
        return None, None
    if p0 == 0 or p2 == 0:
        return None, None
    pre_ret = p1 / p0 - 1
    post_ret = p3 / p2 - 1
    return float(pre_ret), float(post_ret)


def analyze_symbol(sym: str) -> dict:
    db = SessionLocal()
    try:
        funding = _load_funding(db, sym)
        ohlcv = _load_ohlcv_1m(db, sym)
    finally:
        db.close()

    if funding.empty or ohlcv.empty:
        log.warning("[%s] no data", sym)
        return {"symbol": sym, "n_events": 0, "skip_reason": "no_data"}

    events = []
    for _, row in funding.iterrows():
        ts = row["funding_time"]
        fr = row["funding_rate"]
        if abs(fr) < FUNDING_RATE_MIN_ABS:
            continue
        pre_ret, post_ret = _event_returns(ohlcv, ts)
        if pre_ret is None:
            continue
        events.append((ts, fr, pre_ret, post_ret))

    if len(events) < 50:
        return {"symbol": sym, "n_events": len(events), "skip_reason": "too_few_events"}

    df = pd.DataFrame(events, columns=["ts", "fr", "pre_ret", "post_ret"])
    df["fr_sign"] = np.sign(df["fr"])

    # H1: pre-boundary returns OPPOSITE direction of funding
    #     fr_sign × pre_ret should be NEGATIVE on average
    df["pre_aligned_drift"] = df["fr_sign"] * df["pre_ret"]
    pre_mean = df["pre_aligned_drift"].mean()
    pre_t = pre_mean / (df["pre_aligned_drift"].std() / np.sqrt(len(df)))

    # H2: post-boundary mean reversion
    #     If pre drifted opposite (fr_sign × pre < 0), post should be same as fr_sign
    df["post_aligned"] = df["fr_sign"] * df["post_ret"]
    post_mean = df["post_aligned"].mean()
    post_t = post_mean / (df["post_aligned"].std() / np.sqrt(len(df)))

    # H3: stratified by funding sign
    pos = df[df["fr_sign"] > 0]
    neg = df[df["fr_sign"] < 0]
    pos_pre_mean = pos["pre_ret"].mean() if len(pos) else np.nan
    pos_post_mean = pos["post_ret"].mean() if len(pos) else np.nan
    neg_pre_mean = neg["pre_ret"].mean() if len(neg) else np.nan
    neg_post_mean = neg["post_ret"].mean() if len(neg) else np.nan

    # H4: tradeability — simple rule: enter at boundary in fr_sign direction,
    # exit POST_WINDOW_MIN later. Return = fr_sign × post_ret minus fee 2x4bps.
    fee_round_trip = 0.0008
    df["pnl"] = df["fr_sign"] * df["post_ret"] - fee_round_trip
    pnl_mean = df["pnl"].mean()
    pnl_sharpe = pnl_mean / df["pnl"].std() if df["pnl"].std() > 0 else 0
    pnl_ann_sharpe = pnl_sharpe * np.sqrt(365 * 3)  # 3 events per day
    win_rate = (df["pnl"] > 0).mean()

    return {
        "symbol": sym,
        "n_events": len(df),
        "n_pos_fr": int((df["fr_sign"] > 0).sum()),
        "n_neg_fr": int((df["fr_sign"] < 0).sum()),
        "first_event": str(df["ts"].min()),
        "last_event": str(df["ts"].max()),
        "h1_pre_aligned_drift_mean_bps": round(pre_mean * 10000, 3),
        "h1_pre_t_stat": round(pre_t, 2),
        "h2_post_aligned_mean_bps": round(post_mean * 10000, 3),
        "h2_post_t_stat": round(post_t, 2),
        "h3_pos_fr_pre_mean_bps": round(pos_pre_mean * 10000, 3) if not np.isnan(pos_pre_mean) else None,
        "h3_pos_fr_post_mean_bps": round(pos_post_mean * 10000, 3) if not np.isnan(pos_post_mean) else None,
        "h3_neg_fr_pre_mean_bps": round(neg_pre_mean * 10000, 3) if not np.isnan(neg_pre_mean) else None,
        "h3_neg_fr_post_mean_bps": round(neg_post_mean * 10000, 3) if not np.isnan(neg_post_mean) else None,
        "h4_post_strategy_pnl_mean_bps_after_fee": round(pnl_mean * 10000, 3),
        "h4_pnl_sharpe_per_trade": round(pnl_sharpe, 3),
        "h4_pnl_ann_sharpe": round(pnl_ann_sharpe, 2),
        "h4_win_rate": round(win_rate, 3),
    }


def main() -> int:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    results = []
    for sym in SYMBOLS:
        log.info("analyzing %s ...", sym)
        r = analyze_symbol(sym)
        log.info("  → %s", json.dumps({k: v for k, v in r.items() if k not in ("symbol",)}))
        results.append(r)

    # Aggregate cross-symbol summary
    valid = [r for r in results if r.get("n_events", 0) >= 50]
    if valid:
        df = pd.DataFrame(valid)
        agg = {
            "n_symbols_analyzed": len(valid),
            "n_total_events": int(df["n_events"].sum()),
            "h1_pre_t_stat_mean": round(df["h1_pre_t_stat"].mean(), 2),
            "h1_pre_t_stat_median": round(df["h1_pre_t_stat"].median(), 2),
            "h1_n_significant_neg": int((df["h1_pre_t_stat"] < -2.0).sum()),
            "h1_n_significant_pos": int((df["h1_pre_t_stat"] > +2.0).sum()),
            "h4_pnl_ann_sharpe_mean": round(df["h4_pnl_ann_sharpe"].mean(), 2),
            "h4_pnl_ann_sharpe_median": round(df["h4_pnl_ann_sharpe"].median(), 2),
            "h4_n_sharpe_gt_1": int((df["h4_pnl_ann_sharpe"] > 1.0).sum()),
            "h4_n_sharpe_gt_2": int((df["h4_pnl_ann_sharpe"] > 2.0).sum()),
        }
    else:
        agg = {"n_symbols_analyzed": 0}

    out = {"per_symbol": results, "aggregate": agg}
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    log.info("saved → %s", OUT_PATH)
    log.info("AGGREGATE: %s", json.dumps(agg, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
