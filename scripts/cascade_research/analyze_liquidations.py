"""
Liquidation Cascade Analyzer
- Reads JSONL files from data/
- Aggregates per-hour liquidation USD totals
- Classifies cascades by tier
- For top events, fetches BTC/ETH 1m kline from Binance to measure recovery

Usage:
    python3 scripts/cascade_research/analyze_liquidations.py
    python3 scripts/cascade_research/analyze_liquidations.py --symbol BTCUSDT
    python3 scripts/cascade_research/analyze_liquidations.py --top 20 --recovery
"""
import argparse
import json
import logging
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median

DATA_DIR = Path(__file__).parent / "data"

# Tier thresholds in USD per hour (market-wide unless --symbol specified)
TIERS = [
    ("Tier1_Mega", 500_000_000),
    ("Tier2_Large", 200_000_000),
    ("Tier3_Medium", 50_000_000),
    ("Tier4_Small", 20_000_000),
]

# Per-symbol thresholds (for single-coin analysis, much smaller)
SYMBOL_TIERS = [
    ("Tier1_Mega", 50_000_000),
    ("Tier2_Large", 20_000_000),
    ("Tier3_Medium", 5_000_000),
    ("Tier4_Small", 1_000_000),
]

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("liq-analyzer")


def load_records(symbol: str | None = None):
    """Yield all liquidation records from data/, optionally filtered by symbol."""
    files = sorted(DATA_DIR.glob("liquidations_*.jsonl"))
    if not files:
        logger.error(f"No data files in {DATA_DIR}")
        sys.exit(1)
    for f in files:
        with f.open() as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if symbol and rec.get("sym") != symbol:
                    continue
                yield rec


def aggregate_hourly(records):
    """Bucket records into UTC hours -> {long_usd, short_usd, total_usd, count}."""
    buckets = defaultdict(lambda: {"long_usd": 0.0, "short_usd": 0.0, "total_usd": 0.0, "count": 0})
    for r in records:
        ts = datetime.fromtimestamp(r["ts"] / 1000, tz=timezone.utc)
        hour_key = ts.replace(minute=0, second=0, microsecond=0)
        usd = r["usd"]
        if r["side"] == "SELL":  # SELL on liquidation = long position liquidated
            buckets[hour_key]["long_usd"] += usd
        else:
            buckets[hour_key]["short_usd"] += usd
        buckets[hour_key]["total_usd"] += usd
        buckets[hour_key]["count"] += 1
    return buckets


def classify_tiers(hourly, tiers):
    """Group hours into tiers."""
    by_tier = {name: [] for name, _ in tiers}
    by_tier["Below"] = []
    for hour, data in sorted(hourly.items()):
        usd = data["total_usd"]
        placed = False
        for name, threshold in tiers:
            if usd >= threshold:
                by_tier[name].append((hour, data))
                placed = True
                break
        if not placed:
            by_tier["Below"].append((hour, data))
    return by_tier


def fetch_klines(symbol: str, start_ms: int, end_ms: int, interval: str = "1m"):
    """Fetch klines from Binance Futures public API."""
    url = (
        "https://fapi.binance.com/fapi/v1/klines"
        f"?symbol={symbol}&interval={interval}&startTime={start_ms}&endTime={end_ms}&limit=1500"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "cascade-research/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        logger.warning(f"  kline fetch failed for {symbol}: {e}")
        return []


def measure_recovery(symbol: str, hour_dt: datetime):
    """For a given cascade hour, compute drawdown and 6h recovery vs symbol price."""
    start_ms = int((hour_dt - timedelta(hours=1)).timestamp() * 1000)
    end_ms = int((hour_dt + timedelta(hours=6)).timestamp() * 1000)
    klines = fetch_klines(symbol, start_ms, end_ms)
    if len(klines) < 60:
        return None

    # klines: [openTime, open, high, low, close, volume, ...]
    pre_price = float(klines[0][1])  # open of pre-cascade hour
    cascade_lows = [float(k[3]) for k in klines[60:120] if len(klines) > 120]  # cascade hour
    if not cascade_lows:
        return None
    cascade_low = min(cascade_lows)

    post_klines = klines[120:] if len(klines) > 120 else []
    if not post_klines:
        return None
    post_high = max(float(k[2]) for k in post_klines)
    post_close = float(post_klines[-1][4])

    drawdown_pct = (cascade_low - pre_price) / pre_price * 100
    recovery_pct = (post_high - cascade_low) / cascade_low * 100
    net_pct = (post_close - pre_price) / pre_price * 100

    return {
        "pre": pre_price,
        "low": cascade_low,
        "post_high": post_high,
        "post_close": post_close,
        "drawdown_pct": drawdown_pct,
        "recovery_pct": recovery_pct,
        "net_6h_pct": net_pct,
    }


def fmt_usd(x):
    if x >= 1e9:
        return f"${x/1e9:.2f}B"
    if x >= 1e6:
        return f"${x/1e6:.1f}M"
    if x >= 1e3:
        return f"${x/1e3:.1f}K"
    return f"${x:.0f}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", help="Filter to single symbol (e.g., BTCUSDT)")
    p.add_argument("--top", type=int, default=10, help="Show top N hours")
    p.add_argument("--recovery", action="store_true", help="Fetch klines and measure recovery (slow)")
    p.add_argument("--recovery-symbol", default="BTCUSDT", help="Symbol for recovery cross-ref")
    args = p.parse_args()

    records = list(load_records(args.symbol))
    if not records:
        logger.error("No records loaded")
        sys.exit(1)

    first_ts = datetime.fromtimestamp(min(r["ts"] for r in records) / 1000, tz=timezone.utc)
    last_ts = datetime.fromtimestamp(max(r["ts"] for r in records) / 1000, tz=timezone.utc)
    span_hours = (last_ts - first_ts).total_seconds() / 3600
    span_days = span_hours / 24

    print(f"\n{'='*70}")
    print(f"LIQUIDATION CASCADE ANALYSIS")
    print(f"{'='*70}")
    print(f"Records:     {len(records):,}")
    print(f"Symbol:      {args.symbol or 'ALL'}")
    print(f"Span:        {first_ts.isoformat()} → {last_ts.isoformat()}")
    print(f"             {span_hours:.1f}h ({span_days:.2f}d)")
    print(f"Total USD:   {fmt_usd(sum(r['usd'] for r in records))}")

    hourly = aggregate_hourly(records)
    tiers = SYMBOL_TIERS if args.symbol else TIERS
    by_tier = classify_tiers(hourly, tiers)

    print(f"\n{'─'*70}")
    print(f"TIER DISTRIBUTION ({'per-symbol' if args.symbol else 'market-wide'} thresholds)")
    print(f"{'─'*70}")
    print(f"{'Tier':<20} {'Threshold':>12} {'Hours':>8} {'Per Day':>10} {'Per Month':>12}")
    for name, threshold in tiers:
        n = len(by_tier[name])
        per_day = n / span_days if span_days else 0
        per_month = per_day * 30
        print(f"{name:<20} {fmt_usd(threshold):>12} {n:>8} {per_day:>10.2f} {per_month:>12.1f}")
    n_below = len(by_tier["Below"])
    print(f"{'Below_threshold':<20} {'':>12} {n_below:>8} {n_below/span_days if span_days else 0:>10.2f} {n_below/span_days*30 if span_days else 0:>12.1f}")

    print(f"\n{'─'*70}")
    print(f"TOP {args.top} HOURS BY TOTAL LIQUIDATION USD")
    print(f"{'─'*70}")
    sorted_hours = sorted(hourly.items(), key=lambda x: -x[1]["total_usd"])[: args.top]
    print(f"{'UTC Hour':<22} {'Total':>12} {'Long':>12} {'Short':>12} {'L/Total':>8} {'#':>6}")
    for hour, data in sorted_hours:
        long_ratio = data["long_usd"] / data["total_usd"] if data["total_usd"] else 0
        print(
            f"{hour.isoformat():<22} {fmt_usd(data['total_usd']):>12} "
            f"{fmt_usd(data['long_usd']):>12} {fmt_usd(data['short_usd']):>12} "
            f"{long_ratio:>8.2f} {data['count']:>6}"
        )

    if args.recovery and sorted_hours:
        print(f"\n{'─'*70}")
        print(f"RECOVERY ANALYSIS (top {min(args.top, 10)} hours, vs {args.recovery_symbol})")
        print(f"{'─'*70}")
        print(f"{'UTC Hour':<22} {'Drawdown':>10} {'Recovery':>10} {'Net 6h':>10}")
        recoveries = []
        for hour, data in sorted_hours[:10]:
            r = measure_recovery(args.recovery_symbol, hour)
            if r:
                recoveries.append(r)
                print(
                    f"{hour.isoformat():<22} {r['drawdown_pct']:>9.2f}% "
                    f"{r['recovery_pct']:>9.2f}% {r['net_6h_pct']:>9.2f}%"
                )
        if recoveries:
            print(f"\nMean drawdown:  {mean(r['drawdown_pct'] for r in recoveries):.2f}%")
            print(f"Mean recovery:  {mean(r['recovery_pct'] for r in recoveries):.2f}%")
            print(f"Mean net 6h:    {mean(r['net_6h_pct'] for r in recoveries):.2f}%")
            print(f"Median recovery: {median(r['recovery_pct'] for r in recoveries):.2f}%")

    print(f"\n{'─'*70}")
    print(f"TOP SYMBOLS BY LIQUIDATION USD")
    print(f"{'─'*70}")
    sym_totals = defaultdict(float)
    sym_counts = defaultdict(int)
    for r in records:
        sym_totals[r["sym"]] += r["usd"]
        sym_counts[r["sym"]] += 1
    top_syms = sorted(sym_totals.items(), key=lambda x: -x[1])[:15]
    print(f"{'Symbol':<14} {'Total USD':>14} {'Events':>10} {'Avg/Event':>12}")
    for sym, total in top_syms:
        n = sym_counts[sym]
        print(f"{sym:<14} {fmt_usd(total):>14} {n:>10} {fmt_usd(total/n):>12}")

    print()


if __name__ == "__main__":
    main()
