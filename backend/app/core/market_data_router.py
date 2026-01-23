import asyncio
import logging
from typing import Dict, List, Set, Any
from fastapi import WebSocket

logger = logging.getLogger(__name__)

class MarketDataRouter:
    def __init__(self):
        self.listeners: Dict[str, Set[asyncio.Queue]] = {} # symbol -> set of queues
        self.active_subscriptions: Set[str] = set() # Symbols we are listening to from Adapter
        self.live_manager = None # Injected lazily

    def get_instance(self):
        """Singleton Accessor"""
        return self

    def set_live_manager(self, manager):
        self.live_manager = manager

    async def connect(self, websocket: WebSocket, symbol: str):
        await websocket.accept()
        queue = asyncio.Queue(maxsize=100)
        
        if symbol not in self.listeners:
            self.listeners[symbol] = set()
            
        self.listeners[symbol].add(queue)
        
        # Ensure Adapter is listening
        if symbol not in self.active_subscriptions and self.live_manager:
            try:
                # We need access to the adapter. 
                # Ideally LiveManager exposes a method to subscribe to REAL data.
                # Or we access adapter directly if public.
                adapter = self.live_manager.adapter
                if adapter:
                    adapter.register_real_listener(symbol, self._handle_tick)
                    self.active_subscriptions.add(symbol)
                    logger.info(f"MarketDataRouter: Subscribed to {symbol}")
            except Exception as e:
                logger.error(f"Failed to subscribe to {symbol}: {e}")

        try:
            while True:
                data = await queue.get()
                await websocket.send_json(data)
        except Exception:
            pass
        finally:
            self.listeners[symbol].remove(queue)
            if not self.listeners[symbol]:
                del self.listeners[symbol]
                # Optional: Unsubscribe from Adapter if no listeners?
                # For now keep it simple, duplicate subscription is fine or handle clean up later.
                # If we want to unsubscribe:
                # if symbol in self.active_subscriptions and self.live_manager:
                #     self.live_manager.adapter.unregister_real_listener(symbol, self._handle_tick)
                #     self.active_subscriptions.remove(symbol)
            pass

    async def _handle_tick(self, data: Dict[str, Any]):
        """Callback from Adapter"""
        symbol = data.get('symbol')
        if not symbol or symbol not in self.listeners:
            return

        payload = {
            "type": "tick",
            "price": data.get('price', 0),
            "time": data.get('timestamp', ''),
            "volume": int(data.get('volume', 0))
        }

        # Broadcast
        for q in list(self.listeners[symbol]):
            if not q.full():
                q.put_nowait(payload)

# Singleton Instance
market_data_router = MarketDataRouter()
