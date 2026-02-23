"""
Stock List Service - Cached stock list fetching from Kiwoom ka10099 API

Provides a singleton service that fetches and caches the full KOSPI+KOSDAQ
stock list. Cache TTL is 1 hour.

Usage:
    service = StockListService.get_instance()
    stocks = await service.get_stock_list(base_url, token)
"""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from ..core.http_client import HttpClientManager

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 3600  # 1 hour
MARKET_CODES = {"kospi": "0", "kosdaq": "10"}


class StockListService:
    _instance = None

    def __init__(self):
        self._cache: Optional[Dict] = None  # {"data": [...], "fetched_at": datetime}
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _is_cache_valid(self) -> bool:
        if not self._cache:
            return False
        elapsed = (datetime.now() - self._cache["fetched_at"]).total_seconds()
        return elapsed < CACHE_TTL_SECONDS

    async def get_stock_list(self, base_url: str, token: str) -> List[Dict]:
        """Get combined KOSPI + KOSDAQ stock list (cached for 1 hour)."""
        if self._is_cache_valid():
            logger.debug(f"Stock list cache hit: {len(self._cache['data'])} stocks")
            return self._cache["data"]

        async with self._lock:
            # Double-check after acquiring lock
            if self._is_cache_valid():
                return self._cache["data"]

            logger.info("Fetching stock list from ka10099 (KOSPI + KOSDAQ)...")
            all_stocks = []
            for market_name, market_code in MARKET_CODES.items():
                try:
                    stocks = await self._fetch_stock_list(base_url, token, market_code)
                    logger.info(f"  {market_name.upper()}: {len(stocks)} stocks")
                    all_stocks.extend(stocks)
                except Exception as e:
                    logger.error(f"Failed to fetch {market_name} stock list: {e}")

            self._cache = {
                "data": all_stocks,
                "fetched_at": datetime.now()
            }
            logger.info(f"Stock list cached: {len(all_stocks)} total stocks")
            return all_stocks

    async def _fetch_stock_list(self, base_url: str, token: str, market_type: str) -> list:
        """ka10099 API call with pagination (same logic as fetch_new_listings.py)."""
        url = f"{base_url}/api/dostk/stkinfo"
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {token}",
            "api-id": "ka10099",
        }
        payload = {"mrkt_tp": market_type}

        client = HttpClientManager.get_instance().get_client()
        all_items = []
        cont_yn = None
        next_key = None

        while True:
            req_headers = {**headers}
            if cont_yn == "Y" and next_key:
                req_headers["cont-yn"] = "Y"
                req_headers["next-key"] = next_key

            resp = await client.post(url, headers=req_headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

            items = data.get("list", [])
            all_items.extend(items)

            cont_yn = resp.headers.get("cont-yn", data.get("cont-yn", ""))
            next_key = resp.headers.get("next-key", data.get("next-key", ""))

            if cont_yn != "Y" or not next_key:
                break

        return all_items

    def invalidate_cache(self):
        """Force cache refresh on next call."""
        self._cache = None
