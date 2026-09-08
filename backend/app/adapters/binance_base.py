"""
Binance Base Adapter - Shared functionality for Spot and Futures adapters.
- HMAC-SHA256 request signing (no Bearer tokens)
- Server time synchronization
- Rate limiting
- exchangeInfo caching (symbol precision rules)
"""

import hashlib
import hmac
import os
import time
import logging
from typing import Dict, Any, Optional, List
from urllib.parse import urlencode
from collections import deque
import asyncio

logger = logging.getLogger(__name__)

# ⚠ 서명 시각을 찍은 뒤 요청이 서버에 닿기까지의 허용 지연.
#   5초로는 부족했다 — 2026-09-05 18:45 UTC 속도저울 사이클이 호스트 부하로
#   **304초** 걸리면서 `-1021` 이 연달아 터졌고, 만기 청산 하나가 다음
#   사이클로 밀려 롱·숏 다리가 5분 어긋난 채 굳었다. 다음날 10:30 에는
#   같은 `-1021` 이 RSI 지갑 조회를 깨뜨려 후퇴 명목이 쓰였고 `-2019`
#   로 진입이 거절돼 +8% 를 놓쳤다. 이틀에 두 번, 다른 트랙에서 같은 뿌리다.
#   바이낸스 상한은 60000 이다. 재생 공격 창이 넓어지는 대가라 무작정
#   올리지 않고, 실측 지연을 덮는 최소치로 둔다.
RECV_WINDOW_MS = 10_000

# 서버가 **실행하기 전에** 거절하는 시각 오류. 재시도해도 중복 주문이
# 되지 않는 유일한 부류라서 여기만 자동 재시도한다.
_TIMESTAMP_ERRORS = (-1021,)

# ── IP 예산 계측 (2026-09-08 `-1003` 차단 뒤 신설)
#
# 바이낸스 한도는 **API 키가 아니라 IP 기준**이다. 이 호스트는 PM2 58개가
# 한 IP 를 나눠 쓰고 정각·30분에 같이 깨어난다. 그런데 로그에 남는 것은
# 요청 **수**뿐이라, `positionRisk`(가중치 5)와 klines(최대 10)를 구분할 수
# 없어 **누가 예산을 먹는지 추측밖에 못 했다.**
#
# 응답 헤더 `X-MBX-USED-WEIGHT-1M` 이 그 순간의 **IP 전체 사용량**이다.
# 각 프로세스가 자기 요청 수와 함께 남기면 귀속이 된다.
# ⚠ 계측이 스스로 로그 폭풍이 되면 안 된다 — 문턱을 넘을 때와 분당 한 번만.
WEIGHT_WARN = int(os.environ.get("BINANCE_WEIGHT_WARN", "1200"))
WEIGHT_LIMIT = 2400                       # 선물 IP 한도(참고용)
_W_LAST: float = 0.0                      # 마지막 관측 사용량
_W_PEAK: float = 0.0                      # 이번 분의 최고
_W_MIN: int = 0                           # 이번 분(epoch//60)
_W_REQ: int = 0                           # 이번 분 **이 프로세스의** 요청 수
_W_WARN_AT: float = 0.0                   # 마지막 경고 시각(초)


def _note_weight(headers, path: str) -> None:
    """응답 헤더에서 IP 사용량을 읽어 남긴다. **실패해도 조용히 넘어간다.**"""
    global _W_LAST, _W_PEAK, _W_MIN, _W_REQ, _W_WARN_AT
    try:
        raw = None
        for k in ("X-MBX-USED-WEIGHT-1M", "x-mbx-used-weight-1m"):
            raw = headers.get(k)
            if raw:
                break
        now = time.time()
        cur_min = int(now // 60)
        if cur_min != _W_MIN:
            if _W_MIN and _W_PEAK:
                logger.info(
                    f"[IP예산] {_W_MIN % 60:02d}분 최고 {_W_PEAK:.0f}/{WEIGHT_LIMIT} "
                    f"({100 * _W_PEAK / WEIGHT_LIMIT:.0f}%) · 이 프로세스 요청 {_W_REQ}건")
            _W_MIN, _W_PEAK, _W_REQ = cur_min, 0.0, 0
        _W_REQ += 1
        if raw is None:
            return
        w = float(raw)
        _W_LAST = w
        _W_PEAK = max(_W_PEAK, w)
        if w >= WEIGHT_WARN and now - _W_WARN_AT >= 5.0:
            _W_WARN_AT = now
            logger.warning(
                f"[IP예산] **{w:.0f}/{WEIGHT_LIMIT}** ({100 * w / WEIGHT_LIMIT:.0f}%) "
                f"— 이 프로세스가 이번 분 {_W_REQ}건 [{path}]")
    except Exception:                                     # noqa: BLE001
        pass                                              # 계측이 거래를 막지 않는다


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
        p["recvWindow"] = RECV_WINDOW_MS
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

        url = f"{self.api_url}{path}"
        client = HttpClientManager.get_instance().get_client()

        # ⚠ `-1021` 은 서버가 **주문을 실행하기 전에** 거절한 것이다. 그래서
        #   재시도해도 중복 체결이 되지 않는다 — 다른 오류를 여기서 재시도하면
        #   같은 주문을 두 번 낼 수 있으니 부류를 넓히지 마라.
        # ⚠ 재시도는 시각을 **다시 찍는다.** 같은 서명을 되보내면 또 거절된다.
        for attempt in range(2):
            await self._rate_limiter.acquire()

            if signed:
                request_params = self._signed_params(params)
                headers = self._headers()
            else:
                request_params = params or {}
                headers = self._public_headers()

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

            _note_weight(getattr(response, "headers", {}) or {}, path)
            if response.status_code < 400:
                return response.json() if response.content else {}

            error_data = response.json() if response.content else {}
            error_msg = error_data.get("msg", response.text)
            error_code = error_data.get("code", response.status_code)

            retriable = False
            try:
                retriable = int(error_code) in _TIMESTAMP_ERRORS
            except (TypeError, ValueError):
                retriable = False

            if retriable and signed and attempt == 0:
                logger.warning(
                    f"Binance {error_code} timestamp drift [{method} {path}] "
                    f"— resyncing server time and retrying once")
                await self.sync_server_time()
                continue

            logger.error(f"Binance API error: {error_code} {error_msg} [{method} {path}]")
            raise BinanceAPIError(error_code, error_msg)

        # 재시도까지 실패하면 위에서 raise 된다. 여기 도달은 논리 오류다.
        raise BinanceAPIError(-1021, "timestamp retry exhausted")

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
        """호가단위(tickSize)에 맞춘 가격.

        ⚠ 2026-08-22 실계좌에서 드러난 결함 — 이 함수가 **0.0 을 반환**했다.
            tick_size = float("0.000010")  → 1e-05
            str(1e-05) == '1e-05'          → **점이 없다**
            그래서 `'.' in str(tick_size)` 가 False 가 되어 decimals=0,
            `round(0.09618, 0)` = **0.0**. 거래소는 -4001 "Price less than 0"
            으로 거절한다.

          **틱이 0.0001 보다 작은 모든 종목**(저가 알트 대부분)에서 지정가
          주문이 전부 막혀 있었다. 드러나지 않은 건 실거래가 시장가·조건부
          주문만 썼기 때문이다 — 익절 지정가를 처음 쓰면서 발견했다.

          `app/core/qty_rules._count_decimals` 가 이 함정을 이미 대응하고
          있었다(주석에 `str(0.00001) → '1e-05'` 라고 적혀 있다). 자체
          구현 대신 그걸 쓴다 — 같은 계산이 두 곳에 있으면 한 곳만 틀린다.
        """
        from app.core.qty_rules import _count_decimals
        precision = self.get_symbol_precision(symbol)
        tick_size = float(precision.get("tickSize", "0.01"))
        if tick_size <= 0 or price <= 0:
            return price
        dec = _count_decimals(tick_size)
        adjusted = round(round(price / tick_size) * tick_size, dec)
        # ⚠ 양수 가격이 **0 으로 내려가면 안 된다.** 0 은 이 저장소에서
        #   "시장가" 신호로 읽힌다(`_place_order` 의 `if price > 0`). 지정가로
        #   내려던 주문이 조용히 시장가가 되면 슬리피지 전제가 통째로 깨진다.
        #   틱보다 작은 가격은 **한 틱으로 올린다** — 거래소가 거절하게 두는
        #   편이 조용히 시장가로 나가는 것보다 낫다.
        if adjusted <= 0:
            adjusted = round(tick_size, dec)
        return adjusted

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
