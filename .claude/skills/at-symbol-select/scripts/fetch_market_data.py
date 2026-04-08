#!/usr/bin/env python3
"""
Binance 시장 데이터 수집 CLI — backend.app.core.binance_market_snapshot의 thin wrapper.

⚠️ 알고리즘/필터/랭킹 로직 변경은 backend/app/core/binance_market_snapshot.py에서만.
   이 파일은 stdlib(urllib) HTTP 클라이언트 + CLI 어댑터일 뿐.

Usage:
    python fetch_market_data.py                    # 현물
    python fetch_market_data.py --futures          # 선물
    python fetch_market_data.py --min-volume 500000  # 최소 거래량 $500K
    python fetch_market_data.py --summary          # 요약만
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

# ─── Bootstrap: backend on sys.path ──────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent.parent.parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.binance_market_snapshot import (  # noqa: E402
    DEFAULT_MIN_VOLUME,
    build_market_data,
    load_blacklist,
)

# Re-export so legacy `from fetch_market_data import build_market_data` keeps working.
__all__ = ["DEFAULT_MIN_VOLUME", "build_market_data", "load_blacklist", "fetch_tickers"]


SPOT_URL = "https://api.binance.com/api/v3/ticker/24hr"
FUTURES_URL = "https://fapi.binance.com/fapi/v1/ticker/24hr"


def fetch_tickers(futures: bool = False, timeout: int = 15) -> Optional[List[Dict]]:
    """Fetch Binance 24hr tickers via stdlib (no httpx dependency for skill CLI)."""
    url = FUTURES_URL if futures else SPOT_URL
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "antigravity-skill/1.0")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"Error fetching tickers: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(description="Binance 시장 데이터 수집 (backend snapshot wrapper)")
    parser.add_argument("--futures", action="store_true", help="선물 데이터")
    parser.add_argument(
        "--min-volume",
        type=float,
        default=DEFAULT_MIN_VOLUME,
        help=f"최소 거래량 USD (default: {DEFAULT_MIN_VOLUME:,.0f})",
    )
    parser.add_argument("--summary", action="store_true", help="요약만 출력")

    args = parser.parse_args()

    tickers = fetch_tickers(futures=args.futures)
    if tickers is None:
        sys.exit(1)

    blacklist = load_blacklist()
    if blacklist:
        print(
            f"[blacklist] excluded {len(blacklist)} symbols: {sorted(blacklist)}",
            file=sys.stderr,
        )

    stock_data, ranking_data = build_market_data(
        tickers,
        is_futures=args.futures,
        min_volume=args.min_volume,
        blacklist=blacklist,
    )

    if args.summary:
        print(f"Market: {'Futures' if args.futures else 'Spot'}")
        print(f"Total USDT pairs: {len(stock_data)}")
        for key, items in ranking_data.items():
            print(f"  {key}: {len(items)} items")
        print("\nTop 5 by Volume:")
        for item in ranking_data["volume_top"][:5]:
            print(
                f"  {item['code']:12s} ${float(item['quoteVolume']):>16,.0f}  {item['priceChangePercent']}"
            )
    else:
        output = {
            "stock_data": stock_data,
            "ranking_data": ranking_data,
            "meta": {
                "market": "futures" if args.futures else "spot",
                "total_pairs": len(stock_data),
                "min_volume": args.min_volume,
            },
        }
        print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
