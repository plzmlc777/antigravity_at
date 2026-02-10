import asyncio
import json
import logging
import websockets
from typing import Optional, Dict, List, Callable, Any
from datetime import datetime, time
from ..core.config import settings
from .kiwoom_base import KiwoomBaseAdapter
from ..models.live_trading import ErrorType
from ..services.error_logger import error_logger

logger = logging.getLogger(__name__)

# Market Hours Configuration
MARKET_OPEN_TIME = time(9, 0)
MARKET_CLOSE_TIME = time(15, 30)
TICK_HEALTH_CHECK_INTERVAL = 60  # seconds - check for tick health every 60s
TICK_STALE_THRESHOLD = 90  # seconds - if no tick for 90s during market hours, reconnect

class KiwoomWebSocket(KiwoomBaseAdapter):
    """
    WebSocket client for Kiwoom real-time data.

    Phase 4 Change: Removed singleton pattern.
    Each KiwoomRealAdapter now owns its own WebSocket instance,
    enabling true multi-account support with independent connections.
    """

    def __init__(self, app_key: str = None, secret_key: str = None, api_url: str = None):
        # Initialize Base Class with credentials
        KiwoomBaseAdapter.__init__(self, app_key, secret_key)

        # URI from parameter or settings
        self._api_url = api_url or settings.HCP_KIWOOM_API_URL or "https://api.kiwoom.com"
        self.base_url = self._api_url  # Sync for token management
        self.uri = self._build_ws_uri(self._api_url)
        self.websocket = None
        self.is_running = False
        self.monitored_symbols: List[str] = []

        # Per-instance monitor task (no longer class-level)
        self._monitor_task: Optional[asyncio.Task] = None

        # Callbacks (now per-instance, not shared)
        self.on_tick_callback: Optional[Callable[[Dict], None]] = None
        self.on_order_callback: Optional[Callable[[Dict], None]] = None
        self.on_balance_callback: Optional[Callable[[Dict], None]] = None

        # Health Check State
        self.last_tick_time: Optional[datetime] = None
        self._health_check_task: Optional[asyncio.Task] = None

        logger.info(f"WS: Created instance for {self._api_url} (app_key={app_key[:8] if app_key else 'None'}...)")

    def _build_ws_uri(self, api_url: str) -> str:
        """Build WebSocket URI from HTTP API URL"""
        return f"{api_url.replace('https://', 'wss://')}:10000/api/dostk/websocket"

    def update_uri(self, api_url: str):
        """
        Update WebSocket URI based on account's api_url.
        Should be called when active account changes.
        Also clears monitored symbols to prevent cross-account data leakage.
        """
        if not api_url:
            api_url = "https://api.kiwoom.com"

        new_uri = self._build_ws_uri(api_url)
        if new_uri != self.uri:
            logger.info(f"WS: URI updated from {self.uri} to {new_uri}")
            self._api_url = api_url
            self.uri = new_uri
            # Clear symbols when switching accounts to prevent data leakage
            self.clear_symbols()
            return True
        return False

    def clear_symbols(self):
        """Clear all monitored symbols (used on logout/account switch)"""
        old_count = len(self.monitored_symbols)
        self.monitored_symbols.clear()
        self.last_tick_time = None
        logger.info(f"WS: Cleared {old_count} monitored symbols")

    def update_credentials(self, app_key: str, secret_key: str, token: str = None):
        """
        Update credentials for token refresh (used on account switch).

        Args:
            app_key: New app_key
            secret_key: New secret_key
            token: Optional new token (if already acquired)
        """
        self.app_key = app_key
        self.secret_key = secret_key
        self.base_url = self._api_url  # Sync base_url
        if token:
            self.access_token = token
        logger.info(f"WS: Credentials updated for account switch (base_url={self.base_url})")

    @staticmethod
    def is_market_open() -> bool:
        """Check if Korean stock market is currently open (09:00-15:30, weekdays)"""
        now = datetime.now()
        # Weekend check (Saturday=5, Sunday=6)
        if now.weekday() >= 5:
            return False
        # Time check
        current_time = now.time()
        return MARKET_OPEN_TIME <= current_time <= MARKET_CLOSE_TIME
        
    @staticmethod
    def get_instance():
        """
        DEPRECATED: Singleton pattern removed in Phase 4.
        This method exists for backward compatibility only.
        New code should instantiate KiwoomWebSocket directly.
        """
        logger.warning("WS: get_instance() is DEPRECATED. Create instance directly with credentials.")
        return KiwoomWebSocket()

    def set_callbacks(self, 
                      on_tick: Callable[[Dict], None] = None,
                      on_order: Callable[[Dict], None] = None, 
                      on_balance: Callable[[Dict], None] = None):
        self.on_tick_callback = on_tick
        self.on_order_callback = on_order
        self.on_balance_callback = on_balance

    async def connect(self, token: str, app_key: str = None, secret_key: str = None):
        """
        Connect to WebSocket with provided token and credentials.

        Phase 4: Credentials are now passed in __init__, so app_key/secret_key params
        are optional overrides (for backward compatibility).

        Args:
            token: Access token for authentication
            app_key: Optional app_key override (uses __init__ value if not provided)
            secret_key: Optional secret_key override (uses __init__ value if not provided)
        """
        if self.is_running and self.websocket and self.websocket.open:
            logger.info("WS: Already connected and running.")
            # Update credentials even if already connected (for token refresh)
            if app_key and secret_key:
                self.app_key = app_key
                self.secret_key = secret_key
            return

        self.access_token = token

        # Override credentials if provided (backward compatibility)
        if app_key and secret_key:
            self.app_key = app_key
            self.secret_key = secret_key
            self.base_url = self._api_url  # Sync base_url for _ensure_token()
            logger.info(f"WS: Credentials updated for token refresh (base_url={self.base_url})")

        if not self.is_running:
            self.is_running = True
            if self._monitor_task is None or self._monitor_task.done():
                logger.info(f"WS: Starting connection loop to {self.uri}")
                self._monitor_task = asyncio.create_task(self._monitor_connection())
            # Start health check task
            if self._health_check_task is None or self._health_check_task.done():
                self._health_check_task = asyncio.create_task(self._tick_health_check())
        else:
            logger.info("WS: Connection loop already running, token updated.")

    async def _monitor_connection(self):
        retry_count = 0
        first_run = True
        while self.is_running:
            # 0. Mandatory guard delay to prevent tight-looping on fast failures
            #    But skip on first run for faster initial connection
            if not first_run:
                await asyncio.sleep(5)
            first_run = False

            # 1. Ensure we have a valid token (and refresh if needed)
            await self._ensure_token()
            
            if not self.access_token:
                logger.error("WS: No access token available. Waiting 60s...")
                await asyncio.sleep(60)
                continue
                
            # 2. Check token validity (use app_key for account-specific lookup)
            from ..core.token_manager import KiwoomTokenManager
            mgr = KiwoomTokenManager.get_instance()
            remaining_sec = mgr.get_remaining_seconds(self.base_url, self.app_key)

            if remaining_sec < 60:
                logger.warning(f"WS: Token almost expired ({remaining_sec}s). Waiting for refresh...")
                await asyncio.sleep(30)
                continue
            
            try:
                # Kiwoom uses application-level PING (trnm="PING"), not WebSocket protocol pings
                # Disable library auto-ping to avoid premature disconnection
                logger.info(f"WS: Connecting to {self.uri} (Token valid for {remaining_sec // 60} mins)...")
                async with websockets.connect(
                    self.uri,
                    ping_interval=None,
                    ping_timeout=None,
                    close_timeout=10,
                    max_size=2**20,  # 1MB max message size
                ) as websocket:
                    self.websocket = websocket
                    retry_count = 0 # Reset on success
                    
                    logger.info("WS: Connected. Sending LOGIN...")

                    # 0. Send LOGIN
                    login_payload = {
                        "trnm": "LOGIN",
                        "token": self.access_token
                    }
                    await websocket.send(json.dumps(login_payload))

                    # Wait for LOGIN response before sending REGs
                    try:
                        login_resp = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                        login_data = json.loads(login_resp)
                        if login_data.get("return_code") != 0:
                            logger.error(f"WS LOGIN Failed: {login_data.get('return_msg')}")
                            continue
                        logger.info("WS LOGIN Success (confirmed before REG)")
                    except asyncio.TimeoutError:
                        logger.error("WS: LOGIN response timeout")
                        continue

                    # Send Initial Registrations with delay between each
                    # 1. Account Events (Orders/Balance)
                    await self._send_reg([""], ["00", "04"])
                    await asyncio.sleep(0.5)

                    # 2. Symbols
                    if self.monitored_symbols:
                        await self._send_reg(self.monitored_symbols, ["0B"])
                        await asyncio.sleep(0.5)

                    await self._listen_loop()
                    
            except Exception as e:
                retry_count += 1
                wait_time = min(30 * (2 ** (retry_count - 1)), 1800) # 30s, 60s, 120s ... max 30 mins
                logger.error(f"WS: Connection Error: {e}. Retrying in {wait_time}s (Attempt {retry_count})")
                await asyncio.sleep(wait_time)

    async def _listen_loop(self):
        from ..core.token_manager import KiwoomTokenManager
        mgr = KiwoomTokenManager.get_instance()
        msg_count = 0

        try:
            while self.websocket and self.websocket.open:
                try:
                    message = await asyncio.wait_for(self.websocket.recv(), timeout=30.0)
                    msg_count += 1
                    if msg_count <= 3 or msg_count % 100 == 0:
                        logger.info(f"WS: Message #{msg_count}")
                    await self._handle_message(message)
                except asyncio.TimeoutError:
                    # Periodic Token Check while idle
                    remaining = mgr.get_remaining_seconds()
                    if remaining < 1800: # 30 mins
                        logger.info(f"WS: Proactive Refresh - Token expiring soon ({remaining // 60} mins). Reconnecting...")
                        await self.websocket.close()
                        break
                    continue
            # While loop exited (connection closed)
            close_code = getattr(self.websocket, 'close_code', None)
            close_reason = getattr(self.websocket, 'close_reason', None)
            logger.warning(f"WS: Connection ended. close_code={close_code}, close_reason={close_reason}")
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"WS: Connection closed by server. Code={e.code}, Reason={e.reason}")
            error_logger.log_websocket_error(
                message=f"WS: Connection closed by server. Code={e.code}, Reason={e.reason}",
                exception=e,
                context={"close_code": e.code, "close_reason": e.reason}
            )
        except Exception as e:
            logger.error(f"WS: Listen Loop Error: {e}", exc_info=True)
            error_logger.log_websocket_error(
                message=f"WS: Listen Loop Error: {e}",
                exception=e
            )

    async def _handle_message(self, message):
         try:
            data = json.loads(message)
            trnm = data.get("trnm")

            if trnm == "REAL":
                items = data.get("data", [])
                for item in items:
                    m_type = item.get("type")
                    if m_type == "0B":  # Stock Price Tick
                        if self.on_tick_callback:
                            self._parse_tick(item)
                    elif m_type == "00":  # Order Execution Notification (주문체결통보)
                        if self.on_order_callback:
                            self._parse_order_event(item)
                    elif m_type == "04":  # Balance Change Notification (잔고변동통보)
                        if self.on_balance_callback:
                            self._parse_balance_event(item)
                    else:
                        logger.debug(f"WS: Received REAL type {m_type}")
            elif trnm == "REG":
                if data.get("return_code") != 0:
                     logger.error(f"WS REG Error: {data.get('return_msg')}")
                else:
                     logger.info(f"WS REG Success")
            elif trnm == "LOGIN":
                if data.get("return_code") != 0:
                     logger.error(f"WS LOGIN Error: {data.get('return_msg')}")
                else:
                     logger.info("WS LOGIN Success")
            elif trnm == "PING":
                # Responding to PING is essential for maintaining the connection
                await self.websocket.send(message)
            elif trnm == "SYSTEM":
                code = data.get("code", "")
                msg = data.get("message", "")
                logger.warning(f"WS SYSTEM: code={code}, msg={msg}")
                if code == "R10001":
                    # "동일한 App key로 접속이 되었습니다. 기존 세션은 종료가 됩니다"
                    # Another connection with the same App Key was opened.
                    # This session will be closed by the server momentarily.
                    logger.warning("WS: Duplicate session detected. This connection will be closed by server.")
            else:
                logger.debug(f"WS: Unknown trnm={trnm}")
         except Exception as e:
             logger.error(f"WS Parse Error: {e}")

    def _parse_tick(self, item):
        try:
            vals = item.get("values", {})
            # '10' is current price. Removing signs.
            price_str = vals.get("10", "0").strip().replace("+", "").replace("-", "")
            price = float(price_str)
            volume_str = vals.get("13", "0").strip()
            volume = int(volume_str)

            tick = {
                "symbol": item.get("item"),
                "price": price,
                "volume": volume,
                "timestamp": datetime.now().isoformat()
            }
            # Update last tick time for health check
            self.last_tick_time = datetime.now()
            self.on_tick_callback(tick)
        except Exception as e:
            logger.error(f"Tick Parse Error: {e}")
            error_logger.log_websocket_error(
                message=f"Tick Parse Error: {e}",
                exception=e,
                context={"item": item}
            )

    def _parse_order_event(self, item):
        """
        Parse Order Execution Notification (type "00")
        Kiwoom WebSocket 주문체결통보 파싱

        Key fields (based on Kiwoom API docs):
        - 9201: 주문번호 (order_no)
        - 9001: 종목코드 (symbol)
        - 302: 종목명 (name)
        - 913: 주문/체결구분 (order_status: 접수/체결/확인 등)
        - 905: 주문수량 (order_qty)
        - 904: 미체결수량 (unfilled_qty)
        - 908: 체결수량 (filled_qty)
        - 909: 주문가격 (order_price)
        - 910: 체결가격 (exec_price)
        - 901: 매도수구분 (side: 1=매도, 2=매수)
        """
        try:
            vals = item.get("values", {})

            def safe_str(v):
                return str(v).strip() if v else ""

            def safe_int(v):
                if not v:
                    return 0
                s = str(v).strip().replace("+", "").replace("-", "")
                if not s.isdigit():
                    return 0
                return int(s)

            def safe_float(v):
                if not v:
                    return 0.0
                return float(str(v).strip().replace("+", "").replace("-", ""))

            order_event = {
                "event_type": "order",
                "order_no": safe_str(vals.get("9201")),
                "symbol": safe_str(vals.get("9001")),
                "name": safe_str(vals.get("302")),
                "order_status": safe_str(vals.get("913")),  # 접수, 체결, 확인 등
                "side": "SELL" if safe_str(vals.get("901")) in ("1", "매도") else "BUY",
                "order_qty": safe_int(vals.get("905")),
                "order_price": safe_float(vals.get("909")),
                "filled_qty": safe_int(vals.get("908")),
                "exec_price": safe_float(vals.get("910")),
                "unfilled_qty": safe_int(vals.get("904")),
                "timestamp": datetime.now().isoformat(),
                "raw_values": vals  # 디버깅용 원본 데이터
            }

            # 체결 이벤트만 로깅 (접수는 너무 많음)
            if order_event["filled_qty"] > 0:
                logger.info(f"WS Order Fill: {order_event['side']} {order_event['symbol']} "
                           f"qty={order_event['filled_qty']} @ {order_event['exec_price']} "
                           f"(order_no={order_event['order_no']})")
            else:
                logger.debug(f"WS Order Event: {order_event['order_status']} {order_event['symbol']} order_no={order_event['order_no']}")

            self.on_order_callback(order_event)

        except Exception as e:
            logger.error(f"Order Event Parse Error: {e}", exc_info=True)
            error_logger.log_websocket_error(
                message=f"Order Event Parse Error: {e}",
                exception=e,
                context={"item": item}
            )

    def _parse_balance_event(self, item):
        """
        Parse Balance Change Notification (type "04")
        Kiwoom WebSocket 잔고변동통보 파싱

        Key fields:
        - 9001: 종목코드
        - 302: 종목명
        - 930: 보유수량
        - 931: 매입단가
        - 932: 총매입가
        - 933: 현재가
        - 945: 평가손익
        """
        try:
            vals = item.get("values", {})

            def safe_str(v):
                return str(v).strip() if v else ""

            def safe_int(v):
                if not v:
                    return 0
                s = str(v).strip().replace("+", "").replace("-", "")
                if not s.isdigit():
                    return 0
                return int(s)

            def safe_float(v):
                if not v:
                    return 0.0
                return float(str(v).strip().replace("+", "").replace("-", ""))

            balance_event = {
                "event_type": "balance",
                "symbol": safe_str(vals.get("9001")),
                "name": safe_str(vals.get("302")),
                "holding_qty": safe_int(vals.get("930")),
                "avg_price": safe_float(vals.get("931")),
                "total_cost": safe_float(vals.get("932")),
                "current_price": safe_float(vals.get("933")),
                "profit_loss": safe_float(vals.get("945")),
                "timestamp": datetime.now().isoformat(),
                "raw_values": vals
            }

            logger.info(f"WS Balance Update: {balance_event['symbol']} "
                       f"qty={balance_event['holding_qty']} @ avg={balance_event['avg_price']}")

            self.on_balance_callback(balance_event)

        except Exception as e:
            logger.error(f"Balance Event Parse Error: {e}", exc_info=True)
            error_logger.log_websocket_error(
                message=f"Balance Event Parse Error: {e}",
                exception=e,
                context={"item": item}
            )

    async def subscribe_symbols(self, symbols: List[str]):
        if not symbols: return
        new_syms = [s for s in symbols if s not in self.monitored_symbols]
        self.monitored_symbols.extend(new_syms) 
        
        if self.websocket and self.websocket.open:
            await self._send_reg(symbols, ["0B"]) 
            
    async def _send_reg(self, items: List[str], types: List[str]):
        if not self.websocket or not self.websocket.open:
            logger.warning(f"WS: Skip REG (WS not open): {items} {types}")
            return

        logger.info(f"WS: Sending REG for items: {items}, types: {types}")
        payload = {
            "trnm": "REG",
            "grp_no": "1",
            "refresh": "1",
            "data": [{ "item": items, "type": types }]
        }
        await self.websocket.send(json.dumps(payload))

    async def _tick_health_check(self):
        """
        Monitor tick data health during market hours.
        If no tick received for TICK_STALE_THRESHOLD seconds during market hours,
        force reconnection to recover from stale connections.
        """
        logger.info("WS: Tick health check task started")
        while self.is_running:
            try:
                await asyncio.sleep(TICK_HEALTH_CHECK_INTERVAL)

                # Only check during market hours
                if not self.is_market_open():
                    continue

                # Skip if no symbols registered
                if not self.monitored_symbols:
                    continue

                # Check tick staleness
                if self.last_tick_time:
                    elapsed = (datetime.now() - self.last_tick_time).total_seconds()
                    if elapsed > TICK_STALE_THRESHOLD:
                        logger.warning(
                            f"WS Health: No tick for {elapsed:.0f}s during market hours. "
                            f"Triggering reconnection..."
                        )
                        await self._force_reconnect()
                else:
                    # No tick ever received during market hours - might be stale from startup
                    if self.websocket and self.websocket.open:
                        logger.warning("WS Health: Market open but no tick received yet. Re-registering symbols...")
                        await self._send_reg(self.monitored_symbols, ["0B"])

            except asyncio.CancelledError:
                logger.info("WS: Tick health check task cancelled")
                break
            except Exception as e:
                logger.error(f"WS Health Check Error: {e}")
                error_logger.log_websocket_error(
                    message=f"WS Health Check Error: {e}",
                    exception=e
                )
                await asyncio.sleep(10)

    async def _force_reconnect(self):
        """Force close and reconnect the WebSocket"""
        try:
            if self.websocket and self.websocket.open:
                logger.info("WS: Force closing connection for reconnect...")
                await self.websocket.close()
            # Reset tick time so we don't immediately trigger another reconnect
            self.last_tick_time = None
        except Exception as e:
            logger.error(f"WS Force Reconnect Error: {e}")
            error_logger.log_websocket_error(
                message=f"WS Force Reconnect Error: {e}",
                exception=e
            )
