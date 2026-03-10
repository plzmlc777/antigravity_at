"""
Binance Base Adapter - Shared functionality for Spot and Futures adapters.
- HMAC-SHA256 request signing (no Bearer tokens)
- Server time synchronization
- Rate limiting
- exchangeInfo caching (symbol precision rules)
"""

import hashlib
import hmac
import time
import logging
from typing import Dict, Any, Optional, List
from urllib.parse import urlencode
from collections import deque
import asyncio

logger = logging.getLogger(__name__)


class BinanceRateLimiter:
    """Sliding window rate limiter for Binance API.
    Default limits: 1200 req/min for orders, 6000 req/min for general."""

    def __init__(self, max_requests: int = 1200, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: deque = deque()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            # Remove expired timestamps
            while self._timestamps and self._timestamps[0] < now - self.window_seconds:
                self._timestamps.popleft()
            if len(self._timestamps) >= self.max_requests:
                wait_time = self._timestamps[0] + self.window_seconds - now
                if wait_time > 0:
                    logger.warning(f"Rate limit reached, waiting {wait_time:.1f}s")
                    await asyncio.sleep(wait_time)
            self._timestamps.append(time.monotonic())


class BinanceBaseAdapter:
    """
    Shared base for Binance Spot and Futures adapters.
    Handles HMAC-SHA256 signing, time sync, exchangeInfo caching.
    """

    def __init__(self, api_key: str, secret_key: str, api_url: str,
                 account_name: str = "", is_testnet: bool = False):
        self.api_key = api_key
        self.secret_key = secret_key
        self.api_url = api_url.rstrip("/")
        self._account_name = account_name
        self.is_testnet = is_testnet

        # Time sync
        self._time_offset_ms: int = 0  # server_time - local_time
        self._last_time_sync: float = 0

        # exchangeInfo cache
        self._exchange_info: Optional[Dict] = None
        self._symbol_filters: Dict[str, Dict] = {}  # {symbol: {tickSize, stepSize, minNotional}}
        self._exchange_info_loaded: float = 0

        # Rate limiter
        self._rate_limiter = BinanceRateLimiter(max_requests=1200, window_seconds=60)

        # Tick/order listeners (same pattern as Kiwoom adapter)
        self._tick_listeners: List = []
        self._order_listeners: List = []
        self._balance_listeners: List = []

    # ── Signing ──

    def _sign(self, params: Dict[str, Any]) -> str:
        """Generate HMAC-SHA256 signature for request parameters."""
        query_string = urlencode(params)
        return hmac.new(
            self.secret_key.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

    def _get_timestamp(self) -> int:
        """Get server-adjusted timestamp in milliseconds."""
        return int(time.time() * 1000) + self._time_offset_ms

    def _signed_params(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Add timestamp and signature to params."""
        p = dict(params or {})
        p["timestamp"] = self._get_timestamp()
        p["recvWindow"] = 5000
        p["signature"] = self._sign(p)
        return p

    def _headers(self) -> Dict[str, str]:
        """Standard headers for authenticated requests."""
        return {
            "X-MBX-APIKEY": self.api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        }

    def _public_headers(self) -> Dict[str, str]:
        """Headers for public (unauthenticated) requests."""
        return {"Content-Type": "application/json"}

    # ── HTTP helpers ──

    async def _request(self, method: str, path: str, params: Dict = None,
                       signed: bool = True, weight: int = 1) -> Dict[str, Any]:
        """
        Make an authenticated or public API request.
        Uses the global HttpClientManager.
        """
        from ..core.http_client import HttpClientManager

        await self._rate_limiter.acquire()

        url = f"{self.api_url}{path}"

        if signed:
            request_params = self._signed_params(params)
            headers = self._headers()
        else:
            request_params = params or {}
            headers = self._public_headers()

        client = HttpClientManager.get_instance().get_client()

        if method == "GET":
            response = await client.get(url, params=request_params, headers=headers, timeout=30)
        elif method == "POST":
            response = await client.post(url, data=urlencode(request_params), headers=headers, timeout=30)
        elif method == "PUT":
            response = await client.put(url, data=urlencode(request_params), headers=headers, timeout=30)
        elif method == "DELETE":
            response = await client.delete(url, params=request_params, headers=headers, timeout=30)
        else:
            raise ValueError(f"Unsupported method: {method}")

        if response.status_code >= 400:
            error_data = response.json() if response.content else {}
            error_msg = error_data.get("msg", response.text)
            error_code = error_data.get("code", response.status_code)
            logger.error(f"Binance API error: {error_code} {error_msg} [{method} {path}]")
            raise BinanceAPIError(error_code, error_msg)

        return response.json() if response.content else {}

    async def _public_get(self, path: str, params: Dict = None) -> Any:
        """Public GET (no auth)."""
        return await self._request("GET", path, params, signed=False)

    async def _signed_get(self, path: str, params: Dict = None) -> Any:
        """Signed GET."""
        return await self._request("GET", path, params, signed=True)

    async def _signed_post(self, path: str, params: Dict = None) -> Any:
        """Signed POST."""
        return await self._request("POST", path, params, signed=True)

    async def _signed_delete(self, path: str, params: Dict = None) -> Any:
        """Signed DELETE."""
        return await self._request("DELETE", path, params, signed=True)

    async def test_connection(self) -> Dict[str, Any]:
        """Test API key validity. Raises on failure instead of returning defaults."""
        await self._ensure_time_sync()
        # Use account endpoint for signed request validation
        if "fapi" in self.api_url:
            data = await self._signed_get("/fapi/v2/account")
        else:
            data = await self._signed_get("/api/v3/account")
        # Extract balance summary
        cash = {}
        holdings_count = 0
        if "assets" in data:  # Futures
            for asset in data.get("assets", []):
                avail = float(asset.get("availableBalance", 0))
                if avail > 0 or asset["asset"] == "USDT":
                    cash[asset["asset"]] = avail
            holdings_count = sum(1 for p in data.get("positions", []) if float(p.get("positionAmt", 0)) != 0)
        elif "balances" in data:  # Spot
            for b in data.get("balances", []):
                free = float(b.get("free", 0))
                if free > 0:
                    cash[b["asset"]] = free
            holdings_count = len(cash)
        return {"cash": cash, "holdings_count": holdings_count}

    # ── Time Sync ──

    def _time_endpoint(self) -> str:
        """Return the appropriate time endpoint based on API URL."""
        if "fapi" in self.api_url:
            return "/fapi/v1/time"
        return "/api/v3/time"

    async def sync_server_time(self):
        """Synchronize with Binance server time (call periodically)."""
        try:
            data = await self._public_get(self._time_endpoint())
            server_time = data["serverTime"]
            local_time = int(time.time() * 1000)
            self._time_offset_ms = server_time - local_time
            self._last_time_sync = time.time()
            logger.info(f"Binance time sync: offset={self._time_offset_ms}ms")
        except Exception as e:
            logger.warning(f"Time sync failed: {e}")

    async def _ensure_time_sync(self):
        """Sync time if stale (>30 min)."""
        if time.time() - self._last_time_sync > 1800:
            await self.sync_server_time()

    # ── Exchange Info ──

    async def load_exchange_info(self):
        """Load and cache exchangeInfo (symbol precision rules)."""
        try:
            data = await self._public_get("/api/v3/exchangeInfo")
            self._exchange_info = data
            self._exchange_info_loaded = time.time()

            for sym_info in data.get("symbols", []):
                symbol = sym_info["symbol"]
                filters = {}
                for f in sym_info.get("filters", []):
                    if f["filterType"] == "PRICE_FILTER":
                        filters["tickSize"] = f["tickSize"]
                        filters["minPrice"] = f.get("minPrice", "0")
                        filters["maxPrice"] = f.get("maxPrice", "0")
                    elif f["filterType"] == "LOT_SIZE":
                        filters["stepSize"] = f["stepSize"]
                        filters["minQty"] = f.get("minQty", "0")
                        filters["maxQty"] = f.get("maxQty", "0")
                    elif f["filterType"] == "NOTIONAL" or f["filterType"] == "MIN_NOTIONAL":
                        filters["minNotional"] = f.get("minNotional", f.get("minNotional", "0"))
                self._symbol_filters[symbol] = filters

            logger.info(f"Loaded exchangeInfo: {len(self._symbol_filters)} symbols")
        except Exception as e:
            logger.error(f"Failed to load exchangeInfo: {e}")

    async def _ensure_exchange_info(self):
        """Load exchangeInfo if not cached or stale (>24h)."""
        if not self._exchange_info or time.time() - self._exchange_info_loaded > 86400:
            await self.load_exchange_info()

    def get_symbol_precision(self, symbol: str) -> Dict[str, str]:
        """Get precision rules for a symbol."""
        return self._symbol_filters.get(symbol, {
            "tickSize": "0.01",
            "stepSize": "0.00001",
            "minNotional": "5",
        })

    def adjust_quantity(self, symbol: str, quantity: float, price: float = 0) -> float:
        """Adjust quantity using centralized qty_rules (safety net at API boundary)."""
        from ..core.qty_rules import adjust_qty
        filters = self.get_symbol_precision(symbol)
        exchange_name = "BinanceFutures" if "futures" in self.__class__.__name__.lower() else "Binance"
        return adjust_qty(quantity, exchange_name=exchange_name, price=price, symbol_filters=filters)

    def adjust_price(self, symbol: str, price: float) -> float:
        """Round price to symbol's tickSize precision."""
        precision = self.get_symbol_precision(symbol)
        tick_size = float(precision.get("tickSize", "0.01"))
        if tick_size <= 0:
            return price
        adjusted = round(price / tick_size) * tick_size
        decimals = max(0, len(str(tick_size).rstrip('0').split('.')[-1])) if '.' in str(tick_size) else 0
        return round(adjusted, decimals)

    # ── Listener Pattern (same as Kiwoom adapter) ──

    def add_tick_listener(self, callback):
        if callback not in self._tick_listeners:
            self._tick_listeners.append(callback)

    def add_order_listener(self, callback):
        if callback not in self._order_listeners:
            self._order_listeners.append(callback)

    def add_balance_listener(self, callback):
        if callback not in self._balance_listeners:
            self._balance_listeners.append(callback)

    def setup_realtime_callbacks(self):
        """Set up WebSocket callbacks (override in subclass with WS client)."""
        pass

    # ── Initialization ──

    async def initialize(self):
        """Initialize adapter: sync time, load exchange info."""
        await self.sync_server_time()
        await self.load_exchange_info()
        logger.info(f"BinanceBaseAdapter initialized (url={self.api_url}, testnet={self.is_testnet})")


class BinanceAPIError(Exception):
    """Binance API error with code and message."""
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"Binance API Error [{code}]: {message}")
