#!/usr/bin/env python3
"""
Binance 시장 데이터 수집기 — AI 종목 선정용.

바이낸스 24h 티커 데이터를 가져와 stock_data + ranking_data를 JSON으로 출력.
백엔드 ai_symbol_selection.py의 _fetch_binance_market_data()와 동일한 포맷.

Usage:
    python fetch_market_data.py                    # 현물
    python fetch_market_data.py --futures          # 선물
    python fetch_market_data.py --min-volume 500000  # 최소 거래량 $500K
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from typing import Dict, List, Set, Tuple, Optional


SPOT_URL = "https://api.binance.com/api/v3/ticker/24hr"
FUTURES_URL = "https://fapi.binance.com/fapi/v1/ticker/24hr"

DEFAULT_MIN_VOLUME = 100_000  # $100K minimum quote volume

# D-012 (audit 2026-04-06): symbol blacklist applied before any ranking.
BLACKLIST_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "references", "symbol_blacklist.json",
)


def load_blacklist() -> Set[str]:
    """Load symbol blacklist from references/symbol_blacklist.json. Returns empty set on any failure."""
    try:
        with open(BLACKLIST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            str(entry["symbol"]).strip().upper()
            for entry in data.get("blacklist", [])
            if entry.get("symbol")
        }
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"[blacklist] load failed (ignoring): {e}", file=sys.stderr)
        return set()


def fetch_tickers(futures: bool = False, timeout: int = 15) -> Optional[List[Dict]]:
    """Binance 24hr 티커 데이터 가져오기."""
    url = FUTURES_URL if futures else SPOT_URL
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "antigravity-skill/1.0")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"Error fetching tickers: {e}", file=sys.stderr)
        return None


def build_market_data(
    tickers: List[Dict],
    is_futures: bool = False,
    min_volume: float = DEFAULT_MIN_VOLUME,
) -> Tuple[List[Dict], Dict[str, List[Dict]]]:
    """티커 → stock_data + ranking_data 변환 (백엔드 동일 포맷)."""

    # D-012: load blacklist (e.g. SUIUSDT) and exclude before any ranking
    blacklist = load_blacklist()

    # Filter USDT pairs with minimum volume + blacklist
    usdt_tickers = [
        t for t in tickers
        if t.get("symbol", "").endswith("USDT")
        and float(t.get("quoteVolume", 0)) > min_volume
        and t.get("symbol", "").strip().upper() not in blacklist
    ]
    if blacklist:
        print(f"[blacklist] excluded {len(blacklist)} symbols: {sorted(blacklist)}", file=sys.stderr)

    # Build stock_data
    stock_data = []
    for t in usdt_tickers:
        symbol = t["symbol"]
        pct = float(t.get("priceChangePercent", 0))
        stock_data.append({
            "code": symbol,
            "name": symbol.replace("USDT", ""),
            "lastPrice": t.get("lastPrice", "0"),
            "priceChangePercent": f"{pct:+.2f}%",
            "quoteVolume": t.get("quoteVolume", "0"),
            "highPrice": t.get("highPrice", "0"),
            "lowPrice": t.get("lowPrice", "0"),
            "marketName": "Futures" if is_futures else "Spot",
        })

    # Build ranking_data
    def _to_rank(t):
        pct = float(t.get("priceChangePercent", 0))
        return {
            "code": t["symbol"],
            "name": t["symbol"].replace("USDT", ""),
            "lastPrice": t.get("lastPrice", "0"),
            "priceChangePercent": f"{pct:+.2f}%",
            "quoteVolume": t.get("quoteVolume", "0"),
        }

    sorted_volume = sorted(usdt_tickers, key=lambda x: float(x.get("quoteVolume", 0)), reverse=True)
    sorted_change = sorted(usdt_tickers, key=lambda x: float(x.get("priceChangePercent", 0)), reverse=True)

    # Volatility: (high - low) / low
    volatility_data = []
    for t in usdt_tickers:
        high = float(t.get("highPrice", 0))
        low = float(t.get("lowPrice", 0))
        if low > 0:
            vol_pct = ((high - low) / low) * 100
            entry = _to_rank(t)
            entry["volatility"] = f"{vol_pct:.1f}%"
            entry["volatility_val"] = vol_pct
            volatility_data.append(entry)
    volatility_data.sort(key=lambda x: x["volatility_val"], reverse=True)
    for v in volatility_data:
        v.pop("volatility_val", None)

    ranking_data = {
        "volume_top": [_to_rank(t) for t in sorted_volume[:50]],
        "change_top": [_to_rank(t) for t in sorted_change[:30]],
        "change_bottom": [_to_rank(t) for t in sorted_change[-30:]],
        "volatility_top": volatility_data[:30],
    }

    return stock_data, ranking_data


def main():
    parser = argparse.ArgumentParser(description="Binance 시장 데이터 수집")
    parser.add_argument("--futures", action="store_true", help="선물 데이터")
    parser.add_argument("--min-volume", type=float, default=DEFAULT_MIN_VOLUME,
                        help=f"최소 거래량 USD (default: {DEFAULT_MIN_VOLUME:,.0f})")
    parser.add_argument("--summary", action="store_true", help="요약만 출력")

    args = parser.parse_args()

    tickers = fetch_tickers(futures=args.futures)
    if tickers is None:
        sys.exit(1)

    stock_data, ranking_data = build_market_data(
        tickers, is_futures=args.futures, min_volume=args.min_volume
    )

    if args.summary:
        print(f"Market: {'Futures' if args.futures else 'Spot'}")
        print(f"Total USDT pairs: {len(stock_data)}")
        for key, items in ranking_data.items():
            print(f"  {key}: {len(items)} items")
        # Top 5 by volume
        print("\nTop 5 by Volume:")
        for item in ranking_data["volume_top"][:5]:
            print(f"  {item['code']:12s} ${float(item['quoteVolume']):>16,.0f}  {item['priceChangePercent']}")
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
