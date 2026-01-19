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
        self.access_token = token
        self.is_running = True
        logger.info(f"WS: Starting connection loop to {self.uri}")
        asyncio.create_task(self._monitor_connection())

    async def _monitor_connection(self):
        while self.is_running:
            if not self.access_token:
                await asyncio.sleep(2)
                continue
                
            # Validity Check: Do not attempt connection if token is invalid
            if not self.check_token_validity():
                logger.warning("WS: Current token is invalid or expired. Skipping connection attempt to avoid IP blocking. Waiting 60s...")
                await asyncio.sleep(60)
                continue
            
            try:
                # Prepare Headers
                headers = {
                    "api-id": "ws-init", 
                    "Authorization": f"Bearer {self.access_token}",
                    "content-type": "application/json;charset=UTF-8"
                }

                logger.info("WS: Connecting...")
                # Note: websockets 10.0+ uses 'extra_headers', older might use 'additional_headers'.
                # We assume 12.0+ found in environment.
                async with websockets.connect(self.uri, extra_headers=headers) as websocket:
                    self.websocket = websocket
                    logger.info("WS: Connected and Authenticated!")
                    
                    # Send Initial Registrations
                    # 1. Account Events (Orders/Balance)
                    await self._send_reg([""], ["00", "04"])
                    
                    # 2. Symbols
                    if self.monitored_symbols:
                        await self._send_reg(self.monitored_symbols, ["0B"]) 

                    await self._listen_loop()
                    
            except Exception as e:
                logger.error(f"WS: Connection Error: {e}")
                
            await asyncio.sleep(5)

    async def _listen_loop(self):
        try:
            async for message in self.websocket:
                await self._handle_message(message)
        except websockets.exceptions.ConnectionClosed:
            logger.warning("WS: Connection closed by server.")

    async def _handle_message(self, message):
         try:
            data = json.loads(message)
            trnm = data.get("trnm")
            
            if trnm == "REAL":
                items = data.get("data", [])
                for item in items:
                    m_type = item.get("type")
                    if m_type == "0B": # Stock Execution
                        if self.on_tick_callback:
                            self._parse_tick(item)
                    elif m_type == "00": # Order
                        if self.on_order_callback:
                            self.on_order_callback(item)
                    elif m_type == "04": # Balance
                        if self.on_balance_callback:
                            self.on_balance_callback(item)
                            
            elif trnm == "REG":
                if data.get("return_code") != 0:
                     logger.error(f"WS REG Error: {data.get('return_msg')}")
                else:
                     logger.info("WS REG Success")
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
        if not self.websocket or not self.websocket.open: return
        
        payload = {
            "trnm": "REG",
            "grp_no": "1",
            "refresh": "1",
            "data": [{ "item": items, "type": types }]
        }
        await self.websocket.send(json.dumps(payload))
