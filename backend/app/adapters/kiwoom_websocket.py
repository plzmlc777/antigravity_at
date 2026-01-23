import asyncio
import json
import logging
import websockets
from typing import Optional, Dict, List, Callable, Any
from datetime import datetime
from ..core.config import settings
from .kiwoom_base import KiwoomBaseAdapter

logger = logging.getLogger(__name__)

class KiwoomWebSocket(KiwoomBaseAdapter):
    _instance = None
    _monitor_task = None
    
    def __init__(self):
        # Initialize Base Class
        KiwoomBaseAdapter.__init__(self)
        
        self.uri = f"{settings.HCP_KIWOOM_API_URL.replace('https://', 'wss://')}:10000/api/dostk/websocket"
        self.websocket = None
        self.is_running = False
        self.monitored_symbols: List[str] = []
        
        # Callbacks
        self.on_tick_callback: Optional[Callable[[Dict], None]] = None
        self.on_order_callback: Optional[Callable[[Dict], None]] = None
        self.on_balance_callback: Optional[Callable[[Dict], None]] = None
        
    @staticmethod
    def get_instance():
        if KiwoomWebSocket._instance is None:
            KiwoomWebSocket._instance = KiwoomWebSocket()
        return KiwoomWebSocket._instance

    def set_callbacks(self, 
                      on_tick: Callable[[Dict], None] = None,
                      on_order: Callable[[Dict], None] = None, 
                      on_balance: Callable[[Dict], None] = None):
        self.on_tick_callback = on_tick
        self.on_order_callback = on_order
        self.on_balance_callback = on_balance

    async def connect(self, token: str):
        if self.is_running and self.websocket and self.websocket.open:
            logger.info("WS: Already connected and running.")
            return
            
        self.access_token = token
        
        if not self.is_running:
            self.is_running = True
            if KiwoomWebSocket._monitor_task is None or KiwoomWebSocket._monitor_task.done():
                logger.info(f"WS: Starting connection loop to {self.uri}")
                KiwoomWebSocket._monitor_task = asyncio.create_task(self._monitor_connection())
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
                
            # 2. Check token validity
            from ..core.token_manager import KiwoomTokenManager
            mgr = KiwoomTokenManager.get_instance()
            remaining_sec = mgr.get_remaining_seconds()
            
            if remaining_sec < 60:
                logger.warning(f"WS: Token almost expired ({remaining_sec}s). Waiting for refresh...")
                await asyncio.sleep(30)
                continue
            
            try:
                # Official example doesn't use extra headers in connect
                logger.info(f"WS: Connecting to {self.uri} (Token valid for {remaining_sec // 60} mins)...")
                async with websockets.connect(self.uri) as websocket:
                    self.websocket = websocket
                    retry_count = 0 # Reset on success
                    
                    logger.info("WS: Connected. Sending LOGIN...")
                    
                    # 0. Send LOGIN 
                    login_payload = {
                        "trnm": "LOGIN",
                        "refresh": "1",
                        "token": self.access_token
                    }
                    await websocket.send(json.dumps(login_payload))
                    
                    # Wait a moment for server to process LOGIN
                    await asyncio.sleep(1.0)

                    # Send Initial Registrations
                    # 1. Account Events (Orders/Balance)
                    await self._send_reg([""], ["00", "04"])
                    
                    # 2. Symbols
                    if self.monitored_symbols:
                        await self._send_reg(self.monitored_symbols, ["0B"]) 

                    await self._listen_loop()
                    
            except Exception as e:
                retry_count += 1
                wait_time = min(30 * (2 ** (retry_count - 1)), 1800) # 30s, 60s, 120s ... max 30 mins
                logger.error(f"WS: Connection Error: {e}. Retrying in {wait_time}s (Attempt {retry_count})")
                await asyncio.sleep(wait_time)

    async def _listen_loop(self):
        from ..core.token_manager import KiwoomTokenManager
        mgr = KiwoomTokenManager.get_instance()
        
        try:
            while self.websocket and self.websocket.open:
                try:
                    # Use wait_for to allow periodic token checks
                    message = await asyncio.wait_for(self.websocket.recv(), timeout=30.0)
                    await self._handle_message(message)
                except asyncio.TimeoutError:
                    # Periodic Token Check while idle
                    remaining = mgr.get_remaining_seconds()
                    if remaining < 1800: # 30 mins
                        logger.info(f"WS: Proactive Refresh - Token expiring soon ({remaining // 60} mins). Reconnecting...")
                        await self.websocket.close()
                        break
                    continue
        except websockets.exceptions.ConnectionClosed:
            logger.warning("WS: Connection closed by server.")
        except Exception as e:
            logger.error(f"WS: Listen Loop Error: {e}")

    async def _handle_message(self, message):
         try:
            data = json.loads(message)
            trnm = data.get("trnm")
            
            if trnm == "REAL":
                # logger.debug(f"WS: Received REAL message: {data}")
                items = data.get("data", [])
                for item in items:
                    m_type = item.get("type")
                    if m_type == "0B": # Stock Execution
                        # logger.debug(f"WS: Tick received for {item.get('item')}")
                        if self.on_tick_callback:
                            self._parse_tick(item)
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
                # logger.debug("WS: Responded to PING")
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
            self.on_tick_callback(tick)
        except Exception as e:
            logger.error(f"Tick Parse Error: {e}")

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
