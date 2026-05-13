"""Fetch onboardDate per symbol from Binance USDS Futures /fapi/v1/exchangeInfo.

Save to backend/runs/research_track/lifecycle_phase/listing_dates.json
Output: {symbol: {onboard_date: "YYYY-MM-DD", contract_type: "PERPETUAL", quote: "USDT"}}

Usage: python -m scripts.research.fetch_listing_dates
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("fetch_listing_dates")

URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"
OUT_PATH = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"


def main() -> int:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(URL, timeout=30)
    r.raise_for_status()
    data = r.json()
    out: dict[str, dict] = {}
    for s in data.get("symbols", []):
        if s.get("quoteAsset") != "USDT":
            continue
        if s.get("status") != "TRADING":
            continue
        onboard_ms = s.get("onboardDate")
        if not onboard_ms:
            continue
        dt = datetime.fromtimestamp(onboard_ms / 1000, tz=timezone.utc)
        out[s["symbol"]] = {
            "onboard_date": dt.strftime("%Y-%m-%d"),
            "onboard_ts_ms": onboard_ms,
            "contract_type": s.get("contractType", ""),
            "base": s.get("baseAsset", ""),
        }
    OUT_PATH.write_text(json.dumps(out, indent=2, sort_keys=True))
    log.info("Saved %d symbols → %s", len(out), OUT_PATH)

    today = datetime.now(tz=timezone.utc).date()
    by_age = sorted(out.items(), key=lambda kv: kv[1]["onboard_date"], reverse=True)
    log.info("=== 10 youngest perpetual USDT listings ===")
    for sym, meta in by_age[:10]:
        age = (today - datetime.strptime(meta["onboard_date"], "%Y-%m-%d").date()).days
        log.info("  %-18s onboard=%s age=%d days", sym, meta["onboard_date"], age)

    log.info("=== age distribution buckets ===")
    buckets = {"<30d": 0, "30-90d": 0, "90-180d": 0, "180-365d": 0, ">365d": 0}
    for sym, meta in out.items():
        age = (today - datetime.strptime(meta["onboard_date"], "%Y-%m-%d").date()).days
        if age < 30: buckets["<30d"] += 1
        elif age < 90: buckets["30-90d"] += 1
        elif age < 180: buckets["90-180d"] += 1
        elif age < 365: buckets["180-365d"] += 1
        else: buckets[">365d"] += 1
    for k, v in buckets.items():
        log.info("  %s: %d", k, v)
    return 0


if __name__ == "__main__":
    sys.exit(main())
