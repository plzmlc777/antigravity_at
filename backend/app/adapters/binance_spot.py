"""
Binance Spot Adapter - Implements ExchangeInterface for Binance Spot trading.
- Market/Limit orders
- Balance (USDT + holdings)
- Current price
- Outstanding orders
- Fractional quantity support
"""

import asyncio
import logging
from typing import Dict, Any
from ..core.exchange_interface import ExchangeInterface
from .binance_base import BinanceBaseAdapter

logger = logging.getLogger(__name__)


class BinanceSpotAdapter(BinanceBaseAdapter, ExchangeInterface):
    """
    Binance Spot exchange adapter.
    Implements the ExchangeInterface for unified strategy execution.
    """

    def __init__(self, api_key: str, secret_key: str, api_url: str,
                 account_name: str = "", is_testnet: bool = False):
        BinanceBaseAdapter.__init__(
            self, api_key=api_key, secret_key=secret_key,
            api_url=api_url, account_name=account_name, is_testnet=is_testnet
        )
        self.ws_client = None  # Set by LiveManager

    # ── ExchangeInterface Implementation ──

    def get_name(self) -> str:
        return "BINANCE"

    def get_account_name(self) -> str:
        return self._account_name

    async def get_current_price(self, symbol: str) -> Dict[str, Any]:
        """Get current market price for a symbol."""
        try:
            data = await self._public_get("/api/v3/ticker/price", {"symbol": symbol})
            price = float(data.get("price", 0))
            return {
                "name": symbol,
                "price": price,
                "symbol": symbol,
            }
        except Exception as e:
            logger.error(f"get_current_price({symbol}) failed: {e}")
            return {"name": symbol, "price": 0, "symbol": symbol}

    async def get_balance(self) -> Dict[str, Any]:
        """
        Get account balance.
        Returns format compatible with LiveContext:
        {
            "cash": {"USDT": 10000.0, "BTC": 0.5, ...},
            "holdings": {
                "BTCUSDT": {"quantity": 0.5, "avg_price": 60000, "current_price": 67000, ...}
            }
        }
        """
        await self._ensure_time_sync()

        try:
            data = await self._signed_get("/api/v3/account")

            # Parse free balances (non-zero)
            cash = {}
            for bal in data.get("balances", []):
                free = float(bal.get("free", 0))
                locked = float(bal.get("locked", 0))
                total = free + locked
                if total > 0:
                    cash[bal["asset"]] = free  # Available balance (excluding locked in orders)

            # Holdings: assets that aren't the quote currency
            # For spot, "holdings" means non-USDT assets
            holdings = {}
            for asset, amount in cash.items():
                if asset in ("USDT", "BUSD", "USDC"):
                    continue
                if amount > 0:
                    # Try to get current price for this asset
                    try:
                        ticker = await self._public_get("/api/v3/ticker/price", {"symbol": f"{asset}USDT"})
                        current_price = float(ticker.get("price", 0))
                    except Exception:
                        current_price = 0

                    holdings[f"{asset}USDT"] = {
                        "quantity": amount,
                        "avg_price": 0,  # Binance doesn't provide avg cost natively
                        "current_price": current_price,
                        "profit_rate": 0,
                        "profit_amount": 0,
                    }

            return {"cash": cash, "holdings": holdings}

        except Exception as e:
            logger.error(f"get_balance() failed: {e}")
            return {"cash": {"USDT": 0}, "holdings": {}}

    async def place_buy_order(self, symbol: str, price: float, quantity: float) -> Dict[str, Any]:
        """Place a buy order (market if price=0, limit otherwise)."""
        return await self._place_order(symbol, "BUY", price, quantity)

    async def place_sell_order(self, symbol: str, price: float, quantity: float) -> Dict[str, Any]:
        """Place a sell order (market if price=0, limit otherwise)."""
        return await self._place_order(symbol, "SELL", price, quantity)

    async def get_outstanding_orders(self) -> list:
        """Get list of open orders."""
        await self._ensure_time_sync()
        try:
            orders = await self._signed_get("/api/v3/openOrders")
            return [{
                "order_id": str(o["orderId"]),
                "symbol": o["symbol"],
                "side": o["side"],
                "price": float(o["price"]),
                "quantity": float(o["origQty"]),
                "filled_quantity": float(o["executedQty"]),
                "status": o["status"],
                "time": o.get("time", 0),
            } for o in orders]
        except Exception as e:
            logger.error(f"get_outstanding_orders() failed: {e}")
            return []

    async def cancel_order(self, order_id: str, symbol: str, quantity: int = 0,
                           origin_order_id: str = "") -> Dict[str, Any]:
        """Cancel an open order."""
        await self._ensure_time_sync()
        try:
            result = await self._signed_delete("/api/v3/order", {
                "symbol": symbol,
                "orderId": int(order_id),
            })
            return {
                "status": "success",
                "order_id": str(result.get("orderId", order_id)),
                "symbol": symbol,
            }
        except Exception as e:
            logger.error(f"cancel_order({order_id}, {symbol}) failed: {e}")
            return {"status": "failed", "message": str(e)}

    # ── Internal Order Logic ──

    async def _place_order(self, symbol: str, side: str, price: float, quantity: float) -> Dict[str, Any]:
        """
        Place an order on Binance Spot.
        - price > 0: LIMIT order (GTC)
        - price == 0: MARKET order
        """
        await self._ensure_time_sync()
        await self._ensure_exchange_info()

        # Adjust quantity to symbol precision (with minNotional check)
        adj_qty = self.adjust_quantity(symbol, quantity, price=price)
        if adj_qty <= 0:
            return {"status": "failed", "message": f"Quantity too small after adjustment: {quantity} → {adj_qty}"}

        params = {
            "symbol": symbol,
            "side": side,
            "quantity": str(adj_qty),
            "newOrderRespType": "FULL",  # Get fill details immediately
        }

        if price > 0:
            # LIMIT order
            adj_price = self.adjust_price(symbol, price)
            params["type"] = "LIMIT"
            params["timeInForce"] = "GTC"
            params["price"] = str(adj_price)
        else:
            # MARKET order
            params["type"] = "MARKET"

        try:
            result = await self._signed_post("/api/v3/order", params)

            # Parse fill info
            fills = result.get("fills", [])
            avg_fill_price = 0
            total_qty = float(result.get("executedQty", 0))
            if fills:
                total_cost = sum(float(f["price"]) * float(f["qty"]) for f in fills)
                avg_fill_price = total_cost / total_qty if total_qty > 0 else 0
            elif result.get("price"):
                avg_fill_price = float(result["price"])

            order_status = result.get("status", "NEW")
            status = "success" if order_status in ("FILLED", "NEW", "PARTIALLY_FILLED") else "failed"

            logger.info(f"Binance {side} {symbol}: qty={adj_qty}, price={avg_fill_price:.2f}, status={order_status}")

            return {
                "status": status,
                "order_id": str(result.get("orderId", "")),
                "symbol": symbol,
                "side": side.lower(),
                "price": avg_fill_price,
                "quantity": total_qty if total_qty > 0 else adj_qty,
                "order_status": order_status,
            }

        except Exception as e:
            logger.error(f"Binance {side} {symbol} failed: {e}")
            return {"status": "failed", "message": str(e)}

    # ── Chart Data (adapter-level access) ──

    async def get_minute_candles(self, symbol: str, interval: str = "1", count: int = 200, interval_minutes: int = None) -> list:
        """Fetch recent candles via REST API (for live engine warm-up)."""
        if interval_minutes is not None:
            interval = str(interval_minutes)
        interval_map = {"1": "1m", "3": "3m", "5": "5m", "15": "15m", "30": "30m", "60": "1h"}
        binance_interval = interval_map.get(interval, f"{interval}m")

        try:
            data = await self._public_get("/api/v3/klines", {
                "symbol": symbol,
                "interval": binance_interval,
                "limit": min(count, 1000),
            })
            candles = []
            for k in data:
                from datetime import datetime, timezone
                ts = datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc)
                candles.append({
                    "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                })
            return candles
        except Exception as e:
            logger.error(f"get_minute_candles({symbol}) failed: {e}")
            return []

    # ── WebSocket Integration ──

    def setup_realtime_callbacks(self):
        """Bind WebSocket callbacks to adapter listeners."""
        if self.ws_client:
            self.ws_client.set_callbacks(
                on_tick=self._on_ws_tick,
                on_order=self._on_ws_order,
                on_balance=self._on_ws_balance,
            )

    async def start_realtime(self, symbols: list = None):
        """Start Binance Spot WebSocket and subscribe to symbols."""
        from .binance_websocket import BinanceWebSocket

        if not self.ws_client:
            self.ws_client = BinanceWebSocket(
                api_key=self.api_key,
                secret_key=self.secret_key,
                api_url=self.api_url,
                is_testnet=self.is_testnet,
                is_futures=False,
            )
            self.setup_realtime_callbacks()

        if symbols:
            await self.ws_client.subscribe_symbols(symbols)

        if not self.ws_client.is_running:
            await self.ws_client.connect()
            logger.info(f"Binance Spot WebSocket started for {symbols}")

    async def stop_realtime(self):
        """Stop Binance Spot WebSocket."""
        if self.ws_client:
            await self.ws_client.disconnect()
            logger.info("Binance Spot WebSocket stopped")

    async def _on_ws_tick(self, tick_data: Dict):
        """Route tick to listeners."""
        for listener in self._tick_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    asyncio.create_task(listener(tick_data))
                else:
                    listener(tick_data)
            except Exception as e:
                logger.error(f"Tick listener error: {e}")

    async def _on_ws_order(self, order_data: Dict):
        """Route order event to listeners."""
        for listener in self._order_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    asyncio.create_task(listener(order_data))
                else:
                    listener(order_data)
            except Exception as e:
                logger.error(f"Order listener error: {e}")

    async def get_order_executions(self, order_no: str = "", symbol: str = "") -> list:
        """Get recent trade/fill history from Binance Spot."""
        await self._ensure_time_sync()
        try:
            if not symbol:
                return []
            trades = await self._signed_get("/api/v3/myTrades", {
                "symbol": symbol, "limit": 50,
            })
            results = []
            for t in trades:
                results.append({
                    "order_no": str(t.get("orderId", "")),
                    "symbol": t.get("symbol", ""),
                    "side": "BUY" if t.get("isBuyer") else "SELL",
                    "filled_price": float(t.get("price", 0)),
                    "filled_qty": float(t.get("qty", 0)),
                    "commission": float(t.get("commission", 0)),
                    "time": t.get("time", 0),
                })
            return results
        except Exception as e:
            logger.error(f"get_order_executions() failed: {e}")
            return []

    async def _on_ws_balance(self, balance_data: Dict):
        """Route balance event to listeners."""
        for listener in self._balance_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    asyncio.create_task(listener(balance_data))
                else:
                    listener(balance_data)
            except Exception as e:
                logger.error(f"Balance listener error: {e}")
