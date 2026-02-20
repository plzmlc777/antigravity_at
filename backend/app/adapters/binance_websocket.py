"""
Binance WebSocket Client
- Market data stream: trade ticks (no auth required)
- User data stream: order fills, balance updates (listenKey required)
- Auto-reconnect with exponential backoff
- listenKey keepalive (30min interval, 24h max)
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime

logger = logging.getLogger(__name__)

# WebSocket URLs
BINANCE_WS_URLS = {
    "spot_real": "wss://stream.binance.com:9443/ws",
    "spot_testnet": "wss://testnet.binance.vision/ws",
    "futures_real": "wss://fstream.binance.com/ws",
    "futures_testnet": "wss://stream.binancefuture.com/ws",
}


class BinanceWebSocket:
    """
    Binance WebSocket client for real-time data.
    Handles both public market streams and authenticated user data streams.
    """

    def __init__(self, api_key: str = "", secret_key: str = "",
                 api_url: str = "https://api.binance.com",
                 is_testnet: bool = False, is_futures: bool = False):
        self.api_key = api_key
        self.secret_key = secret_key
        self.api_url = api_url
        self.is_testnet = is_testnet
        self.is_futures = is_futures

        # Determine WS URL
        if is_futures:
            self.ws_base = BINANCE_WS_URLS["futures_testnet" if is_testnet else "futures_real"]
        else:
            self.ws_base = BINANCE_WS_URLS["spot_testnet" if is_testnet else "spot_real"]

        # State
        self.is_running = False
        self._ws = None
        self._listen_key: Optional[str] = None
        self._listen_key_created: float = 0
        self._monitored_symbols: List[str] = []
        self._reconnect_delay = 5

        # Callbacks
        self.on_tick_callback: Optional[Callable] = None
        self.on_order_callback: Optional[Callable] = None
        self.on_balance_callback: Optional[Callable] = None

        # Tasks
        self._stream_task: Optional[asyncio.Task] = None
        self._keepalive_task: Optional[asyncio.Task] = None

        # Health
        self.last_tick_time: float = 0

    def set_callbacks(self, on_tick=None, on_order=None, on_balance=None):
        """Set event callbacks."""
        self.on_tick_callback = on_tick
        self.on_order_callback = on_order
        self.on_balance_callback = on_balance

    # ── Public API ──

    async def connect(self):
        """Start WebSocket connections."""
        if self.is_running:
            return
        self.is_running = True

        # Start market data stream
        self._stream_task = asyncio.create_task(self._run_market_stream())

        # Start user data stream if we have credentials
        if self.api_key:
            self._keepalive_task = asyncio.create_task(self._run_user_data_stream())

        logger.info(f"BinanceWebSocket started (testnet={self.is_testnet}, symbols={self._monitored_symbols})")

    async def disconnect(self):
        """Stop all WebSocket connections."""
        self.is_running = False

        if self._stream_task:
            self._stream_task.cancel()
            self._stream_task = None
        if self._keepalive_task:
            self._keepalive_task.cancel()
            self._keepalive_task = None

        # Delete listenKey
        if self._listen_key:
            await self._delete_listen_key()
            self._listen_key = None

        logger.info("BinanceWebSocket stopped")

    async def subscribe_symbols(self, symbols: List[str]):
        """Add symbols to monitor for market data."""
        for s in symbols:
            s_lower = s.lower()
            if s_lower not in self._monitored_symbols:
                self._monitored_symbols.append(s_lower)

        # If already running, reconnect to apply new subscriptions
        if self.is_running and self._stream_task:
            self._stream_task.cancel()
            self._stream_task = asyncio.create_task(self._run_market_stream())

    # ── Market Data Stream (public, no auth) ──

    async def _run_market_stream(self):
        """Main loop for market data WebSocket (trade ticks)."""
        import websockets

        while self.is_running:
            if not self._monitored_symbols:
                await asyncio.sleep(1)
                continue

            # Build combined stream URL
            streams = [f"{s}@trade" for s in self._monitored_symbols]
            stream_path = "/".join(streams)
            url = f"{self.ws_base}/{stream_path}"

            try:
                async with websockets.connect(
                    url,
                    ping_interval=20,
                    ping_timeout=10,
                    max_size=2**20,
                ) as ws:
                    logger.info(f"Market WS connected: {len(self._monitored_symbols)} streams")
                    self._reconnect_delay = 5

                    while self.is_running:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=30)
                            data = json.loads(msg)
                            await self._handle_trade(data)
                        except asyncio.TimeoutError:
                            # Send ping to keep alive
                            await ws.ping()
                        except asyncio.CancelledError:
                            return

            except asyncio.CancelledError:
                return
            except Exception as e:
                if self.is_running:
                    logger.warning(f"Market WS error: {e}. Reconnecting in {self._reconnect_delay}s")
                    await asyncio.sleep(self._reconnect_delay)
                    self._reconnect_delay = min(self._reconnect_delay * 2, 300)

    async def _handle_trade(self, data: Dict):
        """Parse trade event and invoke tick callback."""
        # Single stream format: {"e": "trade", "s": "BTCUSDT", "p": "67000.50", ...}
        # Combined stream format: {"stream": "btcusdt@trade", "data": {...}}
        if "data" in data:
            data = data["data"]

        if data.get("e") != "trade":
            return

        tick = {
            "symbol": data["s"],                    # BTCUSDT
            "price": float(data["p"]),              # Trade price
            "volume": float(data["q"]),             # Trade quantity
            "timestamp": datetime.now().isoformat(),
            "trade_id": data.get("t"),
        }

        self.last_tick_time = time.time()

        if self.on_tick_callback:
            try:
                if asyncio.iscoroutinefunction(self.on_tick_callback):
                    await self.on_tick_callback(tick)
                else:
                    self.on_tick_callback(tick)
            except Exception as e:
                logger.error(f"Tick callback error: {e}")

    # ── User Data Stream (authenticated) ──

    async def _run_user_data_stream(self):
        """Main loop for user data WebSocket (orders, balance)."""
        import websockets

        while self.is_running:
            try:
                # Get or refresh listenKey
                await self._ensure_listen_key()
                if not self._listen_key:
                    logger.warning("Failed to get listenKey, retrying in 30s")
                    await asyncio.sleep(30)
                    continue

                url = f"{self.ws_base}/{self._listen_key}"

                async with websockets.connect(
                    url,
                    ping_interval=20,
                    ping_timeout=10,
                    max_size=2**20,
                ) as ws:
                    logger.info("User data WS connected")
                    self._reconnect_delay = 5

                    # Start keepalive task
                    keepalive = asyncio.create_task(self._keepalive_loop())

                    try:
                        while self.is_running:
                            try:
                                msg = await asyncio.wait_for(ws.recv(), timeout=60)
                                data = json.loads(msg)
                                await self._handle_user_event(data)
                            except asyncio.TimeoutError:
                                continue
                            except asyncio.CancelledError:
                                return
                    finally:
                        keepalive.cancel()

            except asyncio.CancelledError:
                return
            except Exception as e:
                if self.is_running:
                    logger.warning(f"User data WS error: {e}. Reconnecting in {self._reconnect_delay}s")
                    self._listen_key = None  # Force refresh
                    await asyncio.sleep(self._reconnect_delay)
                    self._reconnect_delay = min(self._reconnect_delay * 2, 300)

    async def _handle_user_event(self, data: Dict):
        """Parse user data events (order updates, balance changes)."""
        event_type = data.get("e")

        if event_type == "executionReport":
            # Order update
            order_event = {
                "event_type": "order",
                "order_no": str(data.get("i", "")),     # orderId
                "symbol": data.get("s", ""),              # symbol
                "side": data.get("S", ""),                # BUY/SELL
                "order_status": data.get("X", ""),        # FILLED, NEW, CANCELED, etc.
                "order_qty": float(data.get("q", 0)),     # original qty
                "order_price": float(data.get("p", 0)),   # order price
                "filled_qty": float(data.get("z", 0)),    # cumulative filled qty
                "exec_price": float(data.get("L", 0)),    # last executed price
                "unfilled_qty": float(data.get("q", 0)) - float(data.get("z", 0)),
                "timestamp": datetime.now().isoformat(),
                "client_order_id": data.get("c", ""),
            }

            if order_event["filled_qty"] > 0:
                logger.info(f"WS Order: {order_event['side']} {order_event['symbol']} "
                          f"filled={order_event['filled_qty']} @ {order_event['exec_price']}")

            if self.on_order_callback:
                try:
                    if asyncio.iscoroutinefunction(self.on_order_callback):
                        await self.on_order_callback(order_event)
                    else:
                        self.on_order_callback(order_event)
                except Exception as e:
                    logger.error(f"Order callback error: {e}")

        elif event_type == "outboundAccountPosition":
            # Balance update
            balance_event = {
                "event_type": "balance",
                "balances": {
                    b["a"]: {"free": float(b["f"]), "locked": float(b["l"])}
                    for b in data.get("B", [])
                },
                "timestamp": datetime.now().isoformat(),
            }

            if self.on_balance_callback:
                try:
                    if asyncio.iscoroutinefunction(self.on_balance_callback):
                        await self.on_balance_callback(balance_event)
                    else:
                        self.on_balance_callback(balance_event)
                except Exception as e:
                    logger.error(f"Balance callback error: {e}")

        elif event_type == "listenKeyExpired":
            logger.warning("ListenKey expired, will reconnect")
            self._listen_key = None

    # ── ListenKey Management ──

    async def _ensure_listen_key(self):
        """Create or refresh listenKey."""
        if self._listen_key and time.time() - self._listen_key_created < 3000:
            return  # Valid for ~50 min

        await self._create_listen_key()

    async def _create_listen_key(self):
        """Create a new listenKey via REST API."""
        from ..services.http_client import HttpClientManager

        try:
            client = HttpClientManager.get_instance().get_client()

            if self.is_futures:
                url = f"{self.api_url}/fapi/v1/listenKey"
            else:
                url = f"{self.api_url}/api/v3/userDataStream"

            response = await client.post(url, headers={"X-MBX-APIKEY": self.api_key}, timeout=10)

            if response.status_code == 200:
                data = response.json()
                self._listen_key = data["listenKey"]
                self._listen_key_created = time.time()
                logger.info(f"ListenKey created: {self._listen_key[:20]}...")
            else:
                logger.error(f"Create listenKey failed: {response.status_code} {response.text}")
                self._listen_key = None

        except Exception as e:
            logger.error(f"Create listenKey error: {e}")
            self._listen_key = None

    async def _keepalive_listen_key(self):
        """Ping listenKey to extend its lifetime (call every 30 min)."""
        if not self._listen_key:
            return

        from ..services.http_client import HttpClientManager

        try:
            client = HttpClientManager.get_instance().get_client()

            if self.is_futures:
                url = f"{self.api_url}/fapi/v1/listenKey"
            else:
                url = f"{self.api_url}/api/v3/userDataStream"

            response = await client.put(
                url,
                headers={"X-MBX-APIKEY": self.api_key},
                params={"listenKey": self._listen_key},
                timeout=10,
            )

            if response.status_code == 200:
                self._listen_key_created = time.time()
                logger.debug("ListenKey keepalive OK")
            else:
                logger.warning(f"ListenKey keepalive failed: {response.status_code}")
                self._listen_key = None  # Force recreate

        except Exception as e:
            logger.warning(f"ListenKey keepalive error: {e}")

    async def _delete_listen_key(self):
        """Delete listenKey on disconnect."""
        if not self._listen_key:
            return

        from ..services.http_client import HttpClientManager

        try:
            client = HttpClientManager.get_instance().get_client()

            if self.is_futures:
                url = f"{self.api_url}/fapi/v1/listenKey"
            else:
                url = f"{self.api_url}/api/v3/userDataStream"

            await client.delete(
                url,
                headers={"X-MBX-APIKEY": self.api_key},
                params={"listenKey": self._listen_key},
                timeout=10,
            )
            logger.debug("ListenKey deleted")
        except Exception:
            pass  # Best effort

    async def _keepalive_loop(self):
        """Periodically ping listenKey (every 30 minutes)."""
        try:
            while self.is_running:
                await asyncio.sleep(1800)  # 30 minutes
                await self._keepalive_listen_key()
        except asyncio.CancelledError:
            pass
