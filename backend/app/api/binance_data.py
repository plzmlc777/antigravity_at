"""
Binance Public Data API
- Symbol list with search/filter (no auth required)
- Current price lookup
- Used by CryptoSymbolSelector frontend component
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from ..core.http_client import HttpClientManager

logger = logging.getLogger(__name__)
router = APIRouter()

# Cache for exchange info (refreshed on demand, TTL-based)
_symbol_cache = {
    "spot": {"data": None, "timestamp": 0},
    "futures": {"data": None, "timestamp": 0},
}
_CACHE_TTL = 3600  # 1 hour


async def _fetch_exchange_info(market_type: str = "spot") -> list:
    """Fetch and cache symbol list from Binance exchangeInfo"""
    import time

    cache = _symbol_cache[market_type]
    now = time.time()

    if cache["data"] and (now - cache["timestamp"]) < _CACHE_TTL:
        return cache["data"]

    http = HttpClientManager.get_instance().get_client()

    if market_type == "futures":
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    else:
        url = "https://api.binance.com/api/v3/exchangeInfo"

    try:
        resp = await http.get(url)
        if resp.status_code != 200:
            raise HTTPException(502, f"Binance API error: {resp.status_code}")

        data = resp.json()
        symbols = []
        for s in data.get("symbols", []):
            if s.get("status") != "TRADING" and s.get("contractStatus") != "TRADING":
                continue

            symbol_info = {
                "symbol": s["symbol"],
                "baseAsset": s.get("baseAsset", ""),
                "quoteAsset": s.get("quoteAsset", ""),
            }

            # Extract precision info
            for f in s.get("filters", []):
                if f["filterType"] == "PRICE_FILTER":
                    symbol_info["tickSize"] = f.get("tickSize", "0.01")
                elif f["filterType"] == "LOT_SIZE":
                    symbol_info["stepSize"] = f.get("stepSize", "0.001")
                    symbol_info["minQty"] = f.get("minQty", "0.001")
                elif f["filterType"] == "MIN_NOTIONAL":
                    symbol_info["minNotional"] = f.get("minNotional") or f.get("notional", "5")

            symbols.append(symbol_info)

        cache["data"] = symbols
        cache["timestamp"] = now
        logger.info(f"Cached {len(symbols)} {market_type} symbols from Binance")
        return symbols

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch Binance exchangeInfo: {e}")
        # Return cached data if available, even if expired
        if cache["data"]:
            return cache["data"]
        raise HTTPException(502, f"Failed to fetch Binance symbols: {e}")


@router.get("/symbols")
async def get_symbols(
    market: str = "spot",
    quote: str = "USDT",
    search: Optional[str] = None,
    limit: int = 100,
):
    """
    Get Binance tradable symbol list.

    - market: "spot" or "futures"
    - quote: Quote asset filter (default: USDT)
    - search: Search term (e.g., "BTC", "ETH")
    - limit: Max results (default: 100)
    """
    if market not in ("spot", "futures"):
        raise HTTPException(400, "market must be 'spot' or 'futures'")

    all_symbols = await _fetch_exchange_info(market)

    # Filter by quote asset
    filtered = [s for s in all_symbols if s["quoteAsset"] == quote.upper()]

    # Search filter
    if search:
        term = search.upper()
        filtered = [
            s for s in filtered
            if term in s["symbol"] or term in s["baseAsset"]
        ]

    # Sort: exact match first, then alphabetical
    if search:
        term = search.upper()
        filtered.sort(key=lambda s: (
            0 if s["baseAsset"] == term else 1,
            s["symbol"]
        ))
    else:
        filtered.sort(key=lambda s: s["symbol"])

    return {
        "market": market,
        "quote": quote.upper(),
        "total": len(filtered),
        "symbols": filtered[:limit],
    }


@router.get("/price/{symbol}")
async def get_price(symbol: str, market: str = "spot"):
    """Get current price for a Binance symbol"""
    http = HttpClientManager.get_instance().get_client()
    sym = symbol.upper()

    try:
        if market == "futures":
            url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={sym}"
        else:
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={sym}"

        resp = await http.get(url)
        if resp.status_code != 200:
            raise HTTPException(404, f"Symbol not found: {sym}")

        data = resp.json()
        return {
            "symbol": data["symbol"],
            "price": float(data["price"]),
            "market": market,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Failed to get price: {e}")


@router.get("/info/{symbol}")
async def get_symbol_info(symbol: str, market: str = "spot"):
    """Get detailed info for a specific symbol (precision, filters, etc.)"""
    all_symbols = await _fetch_exchange_info(market)
    sym = symbol.upper()

    for s in all_symbols:
        if s["symbol"] == sym:
            return s

    raise HTTPException(404, f"Symbol not found: {sym}")
