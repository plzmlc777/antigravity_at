"""
KIS (Korean Investment Securities) WebSocket Client
- Real-time tick data (H0STCNT0)
- Order execution notifications (H0STCNI0/H0STCNI9) - AES256 encrypted
- PINGPONG keepalive
- Max 41 subscriptions per connection
"""

import asyncio
import json
import logging
from typing import Optional, List, Callable, Dict
from datetime import datetime
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import base64

logger = logging.getLogger(__name__)

# WebSocket URLs
KIS_WS_REAL_URL = "ws://ops.koreainvestment.com:21000/tryitout"
KIS_WS_VIRTUAL_URL = "ws://ops.koreainvestment.com:31000/tryitout"

MAX_SUBSCRIPTIONS = 41


class KISWebSocket:
    """
    WebSocket client for KIS real-time data.
    Per-adapter instance (same pattern as KiwoomWebSocket).
    """

    def __init__(self, app_key: str, app_secret: str, api_url: str,
                 is_virtual: bool = False):
        self.app_key = app_key
        self.app_secret = app_secret
        self.api_url = api_url
        self.is_virtual = is_virtual
        self.ws_url = KIS_WS_VIRTUAL_URL if is_virtual else KIS_WS_REAL_URL

        self.websocket = None
        self.is_running = False
        self.monitored_symbols: List[str] = []

        # Callbacks
        self.on_tick_callback: Optional[Callable] = None
        self.on_order_callback: Optional[Callable] = None
        self.on_balance_callback: Optional[Callable] = None

        # AES decryption keys (set from first encrypted message)
        self._aes_key: Optional[str] = None
        self._aes_iv: Optional[str] = None

        # Health check
        self.last_tick_time: Optional[datetime] = None
        self._listen_task: Optional[asyncio.Task] = None
        self._health_task: Optional[asyncio.Task] = None

    def set_callbacks(self, on_tick=None, on_order=None, on_balance=None):
        self.on_tick_callback = on_tick
        self.on_order_callback = on_order
        self.on_balance_callback = on_balance

    async def connect(self):
        """Connect to KIS WebSocket."""
        if self.is_running:
            return

        try:
            import websockets
        except ImportError:
            logger.error("KIS WS: websockets package not installed")
            return

        # Get approval key
        from ..core.kis_token_manager import KISTokenManager
        mgr = KISTokenManager.get_instance()
        approval_key = await mgr.get_approval_key(
            self.app_key, self.app_secret, self.api_url
        )
        if not approval_key:
            logger.error("KIS WS: Failed to get approval key")
            return

        try:
            self.websocket = await websockets.connect(
                self.ws_url,
                ping_interval=None,
                max_size=2**20,
            )
            self.is_running = True
            self._approval_key = approval_key

            # Subscribe to existing symbols
            for symbol in self.monitored_symbols:
                await self._subscribe(symbol, approval_key)

            # Start listener and health check
            self._listen_task = asyncio.create_task(self._listen_loop())
            self._health_task = asyncio.create_task(self._health_check_loop())

            logger.info(f"KIS WS: Connected to {self.ws_url}")

        except Exception as e:
            logger.error(f"KIS WS: Connection failed: {e}")
            self.is_running = False

    async def subscribe_symbols(self, symbols: List[str]):
        """Subscribe to real-time tick data for symbols."""
        for symbol in symbols:
            if symbol not in self.monitored_symbols:
                if len(self.monitored_symbols) >= MAX_SUBSCRIPTIONS:
                    logger.warning(f"KIS WS: Max subscriptions ({MAX_SUBSCRIPTIONS}) reached")
                    break
                self.monitored_symbols.append(symbol)
                if self.websocket and self.is_running:
                    await self._subscribe(symbol, self._approval_key)

    async def _subscribe(self, symbol: str, approval_key: str):
        """Send subscription message for a symbol."""
        # Subscribe to tick data (H0STCNT0)
        msg = {
            "header": {
                "approval_key": approval_key,
                "custtype": "P",
                "tr_type": "1",
                "content-type": "utf-8",
            },
            "body": {
                "input": {
                    "tr_id": "H0STCNT0",
                    "tr_key": symbol,
                }
            }
        }
        try:
            await self.websocket.send(json.dumps(msg))
            logger.info(f"KIS WS: Subscribed to tick {symbol}")
        except Exception as e:
            logger.error(f"KIS WS: Subscribe failed for {symbol}: {e}")

        # Subscribe to order execution (H0STCNI0 for real, H0STCNI9 for virtual)
        order_tr_id = "H0STCNI9" if self.is_virtual else "H0STCNI0"
        order_msg = {
            "header": {
                "approval_key": approval_key,
                "custtype": "P",
                "tr_type": "1",
                "content-type": "utf-8",
            },
            "body": {
                "input": {
                    "tr_id": order_tr_id,
                    "tr_key": "",  # Empty for order notifications (account-level)
                }
            }
        }
        try:
            await self.websocket.send(json.dumps(order_msg))
        except Exception:
            pass

    async def _listen_loop(self):
        """Main message receiving loop."""
        while self.is_running and self.websocket:
            try:
                message = await asyncio.wait_for(
                    self.websocket.recv(), timeout=60
                )
                await self._handle_message(message)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                if self.is_running:
                    logger.error(f"KIS WS: Listen error: {e}")
                    await self._reconnect()
                break

    async def _handle_message(self, message: str):
        """Parse and dispatch WebSocket message."""
        # PINGPONG keepalive
        if message.strip() == "PINGPONG":
            try:
                await self.websocket.send("PONG")
            except Exception:
                pass
            return

        # Try JSON (subscription response or control message)
        if message.startswith("{"):
            try:
                data = json.loads(message)
                header = data.get("header", {})
                tr_id = header.get("tr_id", "")

                # Check for AES keys in subscription response
                if "encrypt" in str(data).lower():
                    body = data.get("body", {})
                    output = body.get("output", {})
                    if output.get("key"):
                        self._aes_key = output["key"]
                        self._aes_iv = output.get("iv", "")
                        logger.info(f"KIS WS: AES keys received for {tr_id}")
                return
            except json.JSONDecodeError:
                pass

        # Pipe-separated data: encrypt_flag|tr_id|count|data
        parts = message.split("|", 3)
        if len(parts) < 4:
            return

        encrypt_flag = parts[0]
        tr_id = parts[1]
        data_str = parts[3]

        if tr_id == "H0STCNT0":
            # Tick data (not encrypted)
            self._parse_tick(data_str)
        elif tr_id in ("H0STCNI0", "H0STCNI9"):
            # Order execution (encrypted)
            if encrypt_flag == "1" and self._aes_key:
                try:
                    decrypted = self._decrypt_aes(data_str)
                    self._parse_order(decrypted)
                except Exception as e:
                    logger.error(f"KIS WS: AES decrypt failed: {e}")
            else:
                self._parse_order(data_str)

    def _parse_tick(self, data_str: str):
        """Parse tick data (H0STCNT0) - caret-separated fields."""
        fields = data_str.split("^")
        if len(fields) < 20:
            return

        try:
            tick = {
                "symbol": fields[0],
                "time": fields[1],
                "price": abs(int(fields[2])) if fields[2] else 0,
                "change_sign": fields[3],
                "change": abs(int(fields[4])) if fields[4] else 0,
                "change_rate": float(fields[5]) if fields[5] else 0.0,
                "volume": int(fields[12]) if len(fields) > 12 and fields[12] else 0,
                "acml_vol": int(fields[13]) if len(fields) > 13 and fields[13] else 0,
            }

            self.last_tick_time = datetime.now()

            if self.on_tick_callback:
                self.on_tick_callback(tick)

        except (ValueError, IndexError) as e:
            logger.debug(f"KIS WS: Tick parse error: {e}")

    def _parse_order(self, data_str: str):
        """Parse order execution data."""
        fields = data_str.split("^")
        if len(fields) < 20:
            return

        try:
            order_data = {
                "cntg_yn": fields[13] if len(fields) > 13 else "",
                "order_no": fields[1] if len(fields) > 1 else "",
                "symbol": fields[0] if fields[0] else "",
                "side": "buy" if (len(fields) > 4 and fields[4] == "02") else "sell",
                "order_qty": int(fields[5]) if len(fields) > 5 and fields[5] else 0,
                "order_price": float(fields[6]) if len(fields) > 6 and fields[6] else 0,
                "filled_qty": int(fields[7]) if len(fields) > 7 and fields[7] else 0,
                "filled_price": float(fields[8]) if len(fields) > 8 and fields[8] else 0,
            }

            if self.on_order_callback:
                self.on_order_callback(order_data)

        except (ValueError, IndexError) as e:
            logger.debug(f"KIS WS: Order parse error: {e}")

    def _decrypt_aes(self, encrypted_data: str) -> str:
        """Decrypt AES256-CBC encrypted data from KIS WebSocket."""
        if not self._aes_key or not self._aes_iv:
            return encrypted_data

        try:
            key = self._aes_key.encode("utf-8")
            iv = self._aes_iv.encode("utf-8")
            cipher = AES.new(key, AES.MODE_CBC, iv)
            decoded = base64.b64decode(encrypted_data)
            decrypted = unpad(cipher.decrypt(decoded), AES.block_size)
            return decrypted.decode("utf-8")
        except Exception as e:
            logger.error(f"KIS WS: AES decryption failed: {e}")
            return encrypted_data

    async def _health_check_loop(self):
        """Periodic health check - reconnect if stale."""
        while self.is_running:
            await asyncio.sleep(90)
            if not self.is_running:
                break

            if self.last_tick_time and self.monitored_symbols:
                elapsed = (datetime.now() - self.last_tick_time).total_seconds()
                if elapsed > 120 and self._is_market_open():
                    logger.warning(f"KIS WS: No ticks for {elapsed:.0f}s, reconnecting")
                    await self._reconnect()

    async def _reconnect(self):
        """Reconnect WebSocket."""
        logger.info("KIS WS: Reconnecting...")
        try:
            if self.websocket:
                await self.websocket.close()
        except Exception:
            pass

        self.websocket = None
        self.is_running = False

        await asyncio.sleep(5)
        await self.connect()

    @staticmethod
    def _is_market_open() -> bool:
        """Check if Korean market is open (09:00-15:30 KST, weekdays)."""
        now = datetime.now()
        if now.weekday() >= 5:
            return False
        hour_min = now.hour * 100 + now.minute
        return 900 <= hour_min <= 1530

    async def disconnect(self):
        """Gracefully disconnect."""
        self.is_running = False
        if self._listen_task:
            self._listen_task.cancel()
        if self._health_task:
            self._health_task.cancel()
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception:
                pass
            self.websocket = None
        logger.info("KIS WS: Disconnected")
