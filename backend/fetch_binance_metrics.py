"""Binance Futures funding rate + Open Interest + positioning metrics 백필.

Public API (인증 불필요, 모두 30일 한도 except funding):
- /fapi/v1/fundingRate                       : 8h funding, weight 1, limit 1000/req
- /futures/data/openInterestHist             : OI hist, weight 1, limit 500/req
- /futures/data/topLongShortAccountRatio     : Top trader account L/S ratio
- /futures/data/topLongShortPositionRatio    : Top trader position L/S ratio
- /futures/data/globalLongShortAccountRatio  : Global account L/S ratio
- /futures/data/takerlongshortRatio          : Taker buy/sell vol ratio

Usage:
    # funding 1y + OI 5m + LSR + taker (forward collection)
    python3 fetch_binance_metrics.py --symbols BTCUSDT --source all

    # 신규 paradigm 위한 positioning metrics만 (5m granularity, 30일치)
    python3 fetch_binance_metrics.py --symbols HBARUSDT --source positioning --period 5m
"""
import argparse
import os
import sys
import time
from datetime import datetime, timezone, timedelta

import httpx
from sqlalchemy import text

sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import engine  # noqa: E402

BASE = "https://fapi.binance.com"
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "DOGEUSDT", "AVAXUSDT"]


def _get(url: str, params: dict, retries: int = 3, sleep_on_429: float = 30.0):
    """GET with simple retry on 429."""
    for attempt in range(retries):
        r = httpx.get(url, params=params, timeout=15.0)
        if r.status_code == 429:
            print(f"  [429] sleep {sleep_on_429}s and retry...", flush=True)
            time.sleep(sleep_on_429)
            continue
        r.raise_for_status()
        return r
    raise RuntimeError(f"Exhausted retries: {url} {params}")


def fetch_funding_rate(symbol: str, days: int = 365) -> list[dict]:
    """Fetch funding rate records for `days` worth of history (8h granularity).

    Strategy: walk forward by start_time. Each request returns up to 1000 records.
    For 365 days: 365 * 3 = 1095 records → 2 requests.
    """
    end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = end_ms - days * 24 * 3600 * 1000
    url = f"{BASE}/fapi/v1/fundingRate"
    rows: list[dict] = []
    cursor = start_ms
    page = 0
    while cursor < end_ms and page < 50:
        page += 1
        params = {
            "symbol": symbol,
            "startTime": cursor,
            "endTime": end_ms,
            "limit": 1000,
        }
        r = _get(url, params)
        data = r.json()
        if not data:
            break
        for d in data:
            rows.append({
                "symbol": symbol,
                "funding_time": datetime.fromtimestamp(d["fundingTime"] / 1000, tz=timezone.utc).replace(tzinfo=None),
                "funding_rate": d["fundingRate"],
                "mark_price": d.get("markPrice"),
            })
        last_ms = data[-1]["fundingTime"]
        if len(data) < 1000:
            break  # exhausted
        cursor = last_ms + 1  # advance past last record
        time.sleep(0.1)  # gentle pacing
    return rows


def fetch_oi_hist(symbol: str, period: str = "1d", limit: int = 500) -> list[dict]:
    """Fetch Open Interest history. Binance enforces 30-day window for hist data.

    period: "5m" | "15m" | "30m" | "1h" | "2h" | "4h" | "6h" | "12h" | "1d"
    limit: max 500 per request.

    For period=1d, 30 records max (30 days). For period=5m, 30*24*12=8640 records,
    so 18 requests (limit=500). We just walk one window.
    """
    url = f"{BASE}/futures/data/openInterestHist"
    rows: list[dict] = []

    # Single request strategy for 1d/4h/1h: 500 records covers a few days easily.
    # For 5m/15m: would need pagination but Binance only gives last 30d so single call=500 is enough for now.
    params = {
        "symbol": symbol,
        "period": period,
        "limit": limit,
    }
    r = _get(url, params)
    data = r.json()
    for d in data:
        rows.append({
            "symbol": symbol,
            "timestamp": datetime.fromtimestamp(d["timestamp"] / 1000, tz=timezone.utc).replace(tzinfo=None),
            "interval_str": period,
            "sum_open_interest": d["sumOpenInterest"],
            "sum_open_interest_value": d["sumOpenInterestValue"],
        })
    return rows


_PERIOD_MS = {"5m": 5 * 60_000, "15m": 15 * 60_000, "30m": 30 * 60_000,
              "1h": 60 * 60_000, "2h": 120 * 60_000, "4h": 240 * 60_000,
              "6h": 360 * 60_000, "12h": 720 * 60_000, "1d": 1440 * 60_000}


def _paginated_fetch(url: str, base_params: dict, period: str, days: int,
                      transform) -> list[dict]:
    """Walk backwards by endTime to collect up to `days` of period-granular data.

    Binance limits history to 30 days. Each call returns up to 500 records.
    For 30 days × 5m = 8640 records → ~18 calls.
    """
    period_ms = _PERIOD_MS[period]
    end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    horizon_ms = end_ms - days * 24 * 3600 * 1000
    rows: list[dict] = []
    cursor_end = end_ms
    page = 0
    seen_first_ts: int | None = None
    while page < 40:
        page += 1
        params = dict(base_params)
        params["endTime"] = cursor_end
        try:
            r = _get(url, params)
        except Exception as exc:
            print(f"  [page {page}] ERROR: {exc}")
            break
        data = r.json()
        if not data:
            break
        for d in data:
            rows.append(transform(d))
        first_ts = data[0]["timestamp"]
        if seen_first_ts is not None and first_ts >= seen_first_ts:
            break  # no new earlier records (Binance hit 30d wall)
        seen_first_ts = first_ts
        if first_ts <= horizon_ms:
            break
        cursor_end = first_ts - period_ms  # walk back
        time.sleep(0.1)  # gentle pacing
    # de-dup
    seen = set()
    unique_rows = []
    for row in rows:
        key = (row["symbol"], row["timestamp"], row.get("period") or row.get("interval_str"),
               row.get("metric_type") or "")
        if key not in seen:
            seen.add(key)
            unique_rows.append(row)
    return unique_rows


def fetch_long_short_ratio(symbol: str, endpoint: str, metric_type: str,
                            period: str = "5m", days: int = 30) -> list[dict]:
    """Fetch L/S ratio from /futures/data/{endpoint} with pagination.

    endpoint: "topLongShortAccountRatio" | "topLongShortPositionRatio" |
              "globalLongShortAccountRatio"
    metric_type: stored in DB to identify the source
    days: target backfill window (Binance hard caps to ~30 days)
    """
    url = f"{BASE}/futures/data/{endpoint}"
    base_params = {"symbol": symbol, "period": period, "limit": 500}

    def _t(d: dict) -> dict:
        return {
            "symbol": symbol,
            "timestamp": datetime.fromtimestamp(d["timestamp"] / 1000, tz=timezone.utc).replace(tzinfo=None),
            "period": period,
            "metric_type": metric_type,
            "ratio": d.get("longShortRatio"),
            "component_a": d.get("longAccount") or d.get("longPosition"),
            "component_b": d.get("shortAccount") or d.get("shortPosition"),
        }
    return _paginated_fetch(url, base_params, period, days, _t)


def fetch_taker_long_short_ratio(symbol: str, period: str = "5m",
                                  days: int = 30) -> list[dict]:
    """Fetch /futures/data/takerlongshortRatio with pagination."""
    url = f"{BASE}/futures/data/takerlongshortRatio"
    base_params = {"symbol": symbol, "period": period, "limit": 500}

    def _t(d: dict) -> dict:
        return {
            "symbol": symbol,
            "timestamp": datetime.fromtimestamp(d["timestamp"] / 1000, tz=timezone.utc).replace(tzinfo=None),
            "period": period,
            "metric_type": "taker_buy_sell",
            "ratio": d.get("buySellRatio"),
            "component_a": d.get("buyVol"),
            "component_b": d.get("sellVol"),
        }
    return _paginated_fetch(url, base_params, period, days, _t)


def fetch_oi_hist_paginated(symbol: str, period: str = "5m",
                             days: int = 30) -> list[dict]:
    """Paginated OI hist fetch — extends the existing fetch_oi_hist to collect
    full 30-day window at fine granularity (5m → 8640 records → ~18 pages)."""
    url = f"{BASE}/futures/data/openInterestHist"
    base_params = {"symbol": symbol, "period": period, "limit": 500}

    def _t(d: dict) -> dict:
        return {
            "symbol": symbol,
            "timestamp": datetime.fromtimestamp(d["timestamp"] / 1000, tz=timezone.utc).replace(tzinfo=None),
            "interval_str": period,
            "sum_open_interest": d["sumOpenInterest"],
            "sum_open_interest_value": d["sumOpenInterestValue"],
        }
    return _paginated_fetch(url, base_params, period, days, _t)


def insert_funding(rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = text("""
        INSERT INTO binance_funding_rate
            (symbol, funding_time, funding_rate, mark_price)
        VALUES
            (:symbol, :funding_time, :funding_rate, :mark_price)
        ON CONFLICT (symbol, funding_time) DO NOTHING
    """)
    with engine.begin() as conn:
        conn.execute(sql, rows)
    return len(rows)


def insert_oi(rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = text("""
        INSERT INTO binance_open_interest_hist
            (symbol, timestamp, interval_str, sum_open_interest, sum_open_interest_value)
        VALUES
            (:symbol, :timestamp, :interval_str, :sum_open_interest, :sum_open_interest_value)
        ON CONFLICT (symbol, timestamp, interval_str) DO NOTHING
    """)
    with engine.begin() as conn:
        conn.execute(sql, rows)
    return len(rows)


def insert_positioning(rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = text("""
        INSERT INTO binance_positioning_metric
            (symbol, timestamp, period, metric_type, ratio, component_a, component_b)
        VALUES
            (:symbol, :timestamp, :period, :metric_type, :ratio, :component_a, :component_b)
        ON CONFLICT (symbol, timestamp, period, metric_type) DO NOTHING
    """)
    with engine.begin() as conn:
        conn.execute(sql, rows)
    return len(rows)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS), help="comma-separated USDT-perp symbols")
    p.add_argument("--source", choices=["funding", "oi", "positioning", "all"],
                   default="all")
    p.add_argument("--funding-days", type=int, default=365)
    p.add_argument("--oi-period", default="5m", help="5m/15m/30m/1h/2h/4h/6h/12h/1d")
    p.add_argument("--oi-limit", type=int, default=500)
    p.add_argument("--period", default="5m", help="LSR/taker period (5m/15m/30m/1h)")
    p.add_argument("--positioning-days", type=int, default=30,
                   help="positioning backfill horizon (Binance caps at 30)")
    args = p.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    print(f"Symbols: {symbols}")
    print(f"Source: {args.source}")

    grand_funding = 0
    grand_oi = 0
    grand_pos = 0
    for sym in symbols:
        print(f"\n=== {sym} ===")

        if args.source in ("funding", "all"):
            t0 = time.time()
            rows = fetch_funding_rate(sym, days=args.funding_days)
            n = insert_funding(rows)
            elapsed = time.time() - t0
            if rows:
                tr = (rows[0]["funding_time"], rows[-1]["funding_time"])
                print(f"  [funding] fetched={len(rows)}  inserted={n}  range={tr[0]}~{tr[1]}  elapsed={elapsed:.1f}s")
            else:
                print(f"  [funding] empty result (elapsed={elapsed:.1f}s)")
            grand_funding += n

        if args.source in ("oi", "all"):
            t0 = time.time()
            rows = fetch_oi_hist_paginated(sym, period=args.oi_period,
                                            days=args.positioning_days)
            n = insert_oi(rows)
            elapsed = time.time() - t0
            if rows:
                tr = (rows[0]["timestamp"], rows[-1]["timestamp"])
                print(f"  [oi {args.oi_period}] fetched={len(rows)}  inserted={n}  range={tr[0]}~{tr[1]}  elapsed={elapsed:.1f}s")
            else:
                print(f"  [oi {args.oi_period}] empty result (elapsed={elapsed:.1f}s)")
            grand_oi += n

        if args.source in ("positioning", "all"):
            specs = [
                ("topLongShortAccountRatio", "top_long_short_account"),
                ("topLongShortPositionRatio", "top_long_short_position"),
                ("globalLongShortAccountRatio", "global_long_short_account"),
            ]
            for endpoint, metric_type in specs:
                t0 = time.time()
                try:
                    rows = fetch_long_short_ratio(sym, endpoint, metric_type,
                                                   period=args.period,
                                                   days=args.positioning_days)
                    n = insert_positioning(rows)
                    elapsed = time.time() - t0
                    if rows:
                        tr = (rows[0]["timestamp"], rows[-1]["timestamp"])
                        print(f"  [{metric_type} {args.period}] fetched={len(rows)} inserted={n} range={tr[0]}~{tr[1]} elapsed={elapsed:.1f}s")
                    else:
                        print(f"  [{metric_type} {args.period}] empty (elapsed={elapsed:.1f}s)")
                    grand_pos += n
                    time.sleep(0.1)
                except Exception as exc:
                    print(f"  [{metric_type} {args.period}] ERROR: {exc}")
            # taker buy/sell ratio
            t0 = time.time()
            try:
                rows = fetch_taker_long_short_ratio(sym, period=args.period,
                                                     days=args.positioning_days)
                n = insert_positioning(rows)
                elapsed = time.time() - t0
                if rows:
                    tr = (rows[0]["timestamp"], rows[-1]["timestamp"])
                    print(f"  [taker_buy_sell {args.period}] fetched={len(rows)} inserted={n} range={tr[0]}~{tr[1]} elapsed={elapsed:.1f}s")
                else:
                    print(f"  [taker_buy_sell {args.period}] empty (elapsed={elapsed:.1f}s)")
                grand_pos += n
            except Exception as exc:
                print(f"  [taker_buy_sell {args.period}] ERROR: {exc}")

    print(f"\nGrand total: funding={grand_funding}  oi={grand_oi}  positioning={grand_pos}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
