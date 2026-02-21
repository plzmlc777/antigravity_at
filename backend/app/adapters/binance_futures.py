"""
Binance USDM Futures Adapter - Implements FuturesInterface.
- Leverage control (1-125x)
- Long/Short positions
- CROSSED/ISOLATED margin
- Funding rate queries
- Position management (open, close, reduceOnly)
"""

import asyncio
import logging
from typing import Dict, Any
from ..core.futures_interface import FuturesInterface
from .binance_base import BinanceBaseAdapter

logger = logging.getLogger(__name__)

# Futures API paths (different from spot)
FAPI = "/fapi/v1"
FAPI_V2 = "/fapi/v2"


class BinanceFuturesAdapter(BinanceBaseAdapter, FuturesInterface):
    """
    Binance USDM Futures exchange adapter.
    Inherits signing/rate limiting from BinanceBaseAdapter.
    Implements FuturesInterface (which extends ExchangeInterface).
    """

    def __init__(self, api_key: str, secret_key: str, api_url: str,
                 account_name: str = "", is_testnet: bool = False):
        BinanceBaseAdapter.__init__(
            self, api_key=api_key, secret_key=secret_key,
            api_url=api_url, account_name=account_name, is_testnet=is_testnet
        )
        self.ws_client = None

    # ── Futures exchangeInfo override ──

    async def load_exchange_info(self):
        """Load futures exchangeInfo (different endpoint from spot)."""
        try:
            data = await self._public_get(f"{FAPI}/exchangeInfo")
            self._exchange_info = data
            self._exchange_info_loaded = __import__('time').time()

            for sym_info in data.get("symbols", []):
                symbol = sym_info["symbol"]
                filters = {}
                for f in sym_info.get("filters", []):
                    if f["filterType"] == "PRICE_FILTER":
                        filters["tickSize"] = f["tickSize"]
                    elif f["filterType"] == "LOT_SIZE":
                        filters["stepSize"] = f["stepSize"]
                        filters["minQty"] = f.get("minQty", "0")
                    elif f["filterType"] == "MIN_NOTIONAL":
                        filters["minNotional"] = f.get("notional", "5")
                self._symbol_filters[symbol] = filters

            logger.info(f"Loaded futures exchangeInfo: {len(self._symbol_filters)} symbols")
        except Exception as e:
            logger.error(f"Failed to load futures exchangeInfo: {e}")

    # ── ExchangeInterface Implementation ──

    def get_name(self) -> str:
        return "BINANCE_FUTURES"

    def get_account_name(self) -> str:
        return self._account_name

    async def get_current_price(self, symbol: str) -> Dict[str, Any]:
        """Get current mark price for a futures symbol."""
        try:
            data = await self._public_get(f"{FAPI}/ticker/price", {"symbol": symbol})
            price = float(data.get("price", 0))
            return {"name": symbol, "price": price, "symbol": symbol}
        except Exception as e:
            logger.error(f"get_current_price({symbol}) failed: {e}")
            return {"name": symbol, "price": 0, "symbol": symbol}

    async def get_balance(self) -> Dict[str, Any]:
        """
        Get futures account balance.
        Returns: {"cash": {"USDT": available}, "holdings": {symbol: position_info}}
        """
        await self._ensure_time_sync()
        try:
            data = await self._signed_get(f"{FAPI_V2}/account")

            # Parse USDT balance
            cash = {}
            for asset in data.get("assets", []):
                available = float(asset.get("availableBalance", 0))
                if available > 0 or asset["asset"] == "USDT":
                    cash[asset["asset"]] = available

            # Parse open positions
            holdings = {}
            for pos in data.get("positions", []):
                qty = float(pos.get("positionAmt", 0))
                if qty == 0:
                    continue
                symbol = pos["symbol"]
                entry_price = float(pos.get("entryPrice", 0))
                unrealized_pnl = float(pos.get("unrealizedProfit", 0))
                leverage = int(pos.get("leverage", 1))

                holdings[symbol] = {
                    "quantity": qty,  # Positive=LONG, Negative=SHORT
                    "avg_price": entry_price,
                    "current_price": 0,  # Will be updated via tick
                    "profit_rate": 0,
                    "profit_amount": unrealized_pnl,
                    "leverage": leverage,
                    "margin_type": pos.get("marginType", "cross").upper(),
                    "position_side": "LONG" if qty > 0 else "SHORT",
                }

            return {"cash": cash, "holdings": holdings}

        except Exception as e:
            logger.error(f"get_balance() failed: {e}")
            return {"cash": {"USDT": 0}, "holdings": {}}

    async def place_buy_order(self, symbol: str, price: float, quantity: float) -> Dict[str, Any]:
        """Place a long buy order."""
        return await self._place_order(symbol, "BUY", price, quantity)

    async def place_sell_order(self, symbol: str, price: float, quantity: float) -> Dict[str, Any]:
        """Place a sell order (close long or take profit)."""
        return await self._place_order(symbol, "SELL", price, quantity)

    async def get_outstanding_orders(self) -> list:
        """Get open futures orders."""
        await self._ensure_time_sync()
        try:
            orders = await self._signed_get(f"{FAPI}/openOrders")
            return [{
                "order_id": str(o["orderId"]),
                "symbol": o["symbol"],
                "side": o["side"],
                "price": float(o["price"]),
                "quantity": float(o["origQty"]),
                "filled_quantity": float(o["executedQty"]),
                "status": o["status"],
                "time": o.get("time", 0),
                "position_side": o.get("positionSide", "BOTH"),
            } for o in orders]
        except Exception as e:
            logger.error(f"get_outstanding_orders() failed: {e}")
            return []

    async def cancel_order(self, order_id: str, symbol: str, quantity: int = 0,
                           origin_order_id: str = "") -> Dict[str, Any]:
        """Cancel a futures order."""
        await self._ensure_time_sync()
        try:
            result = await self._signed_delete(f"{FAPI}/order", {
                "symbol": symbol,
                "orderId": int(order_id),
            })
            return {"status": "success", "order_id": str(result.get("orderId", order_id))}
        except Exception as e:
            logger.error(f"cancel_order({order_id}) failed: {e}")
            return {"status": "failed", "message": str(e)}

    # ── FuturesInterface Implementation ──

    async def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """Set leverage for a symbol."""
        await self._ensure_time_sync()
        leverage = max(1, min(leverage, 125))
        try:
            result = await self._signed_post(f"{FAPI}/leverage", {
                "symbol": symbol,
                "leverage": leverage,
            })
            logger.info(f"Leverage set: {symbol} → {leverage}x")
            return {"status": "success", "symbol": symbol, "leverage": result.get("leverage", leverage)}
        except Exception as e:
            logger.error(f"set_leverage({symbol}, {leverage}) failed: {e}")
            return {"status": "failed", "message": str(e)}

    async def get_position(self, symbol: str) -> Dict[str, Any]:
        """Get position info for a specific symbol."""
        await self._ensure_time_sync()
        try:
            positions = await self._signed_get(f"{FAPI_V2}/positionRisk", {"symbol": symbol})

            for pos in positions:
                qty = float(pos.get("positionAmt", 0))
                return {
                    "symbol": pos["symbol"],
                    "side": "LONG" if qty > 0 else ("SHORT" if qty < 0 else "NONE"),
                    "quantity": qty,
                    "entry_price": float(pos.get("entryPrice", 0)),
                    "unrealized_pnl": float(pos.get("unRealizedProfit", 0)),
                    "leverage": int(pos.get("leverage", 1)),
                    "margin_type": pos.get("marginType", "cross").upper(),
                    "liquidation_price": float(pos.get("liquidationPrice", 0)),
                    "mark_price": float(pos.get("markPrice", 0)),
                }

            return {"symbol": symbol, "side": "NONE", "quantity": 0}

        except Exception as e:
            logger.error(f"get_position({symbol}) failed: {e}")
            return {"symbol": symbol, "side": "NONE", "quantity": 0}

    async def place_short_order(self, symbol: str, price: float, quantity: float) -> Dict[str, Any]:
        """Open a short position (SELL to open)."""
        return await self._place_order(symbol, "SELL", price, quantity)

    async def close_position(self, symbol: str) -> Dict[str, Any]:
        """Close entire position with a market order (reduceOnly)."""
        await self._ensure_time_sync()
        await self._ensure_exchange_info()

        try:
            position = await self.get_position(symbol)
            qty = position.get("quantity", 0)

            if qty == 0:
                return {"status": "success", "message": "No position to close"}

            # Close with opposite side
            side = "SELL" if qty > 0 else "BUY"
            abs_qty = abs(qty)
            adj_qty = self.adjust_quantity(symbol, abs_qty)

            params = {
                "symbol": symbol,
                "side": side,
                "type": "MARKET",
                "quantity": str(adj_qty),
                "reduceOnly": "true",
                "newOrderRespType": "RESULT",
            }

            result = await self._signed_post(f"{FAPI}/order", params)
            logger.info(f"Position closed: {symbol} {side} {adj_qty}")

            return {
                "status": "success",
                "order_id": str(result.get("orderId", "")),
                "symbol": symbol,
                "side": side.lower(),
                "quantity": float(result.get("executedQty", adj_qty)),
                "price": float(result.get("avgPrice", 0)),
            }

        except Exception as e:
            logger.error(f"close_position({symbol}) failed: {e}")
            return {"status": "failed", "message": str(e)}

    async def get_funding_rate(self, symbol: str) -> float:
        """Get current funding rate."""
        try:
            data = await self._public_get(f"{FAPI}/fundingRate", {
                "symbol": symbol,
                "limit": 1,
            })
            if data:
                return float(data[0].get("fundingRate", 0))
            return 0.0
        except Exception as e:
            logger.error(f"get_funding_rate({symbol}) failed: {e}")
            return 0.0

    async def set_margin_type(self, symbol: str, margin_type: str) -> Dict[str, Any]:
        """Set margin type (CROSSED or ISOLATED)."""
        await self._ensure_time_sync()
        margin_type = margin_type.upper()
        if margin_type not in ("CROSSED", "ISOLATED"):
            return {"status": "failed", "message": f"Invalid margin type: {margin_type}"}

        try:
            result = await self._signed_post(f"{FAPI}/marginType", {
                "symbol": symbol,
                "marginType": margin_type,
            })
            logger.info(f"Margin type set: {symbol} → {margin_type}")
            return {"status": "success", "symbol": symbol, "margin_type": margin_type}
        except Exception as e:
            # Binance returns error if margin type is already set
            if "No need to change margin type" in str(e):
                return {"status": "success", "symbol": symbol, "margin_type": margin_type}
            logger.error(f"set_margin_type({symbol}, {margin_type}) failed: {e}")
            return {"status": "failed", "message": str(e)}

    async def get_adl_quantile(self, symbol: str) -> int:
        """
        Estimate ADL quantile based on position profitability and leverage.
        Binance doesn't expose ADL quantile directly via REST API,
        so we estimate based on the formula: score = pnl_ratio * leverage.
        Returns 1-5 scale (5 = highest risk of auto-deleveraging).
        """
        try:
            position = await self.get_position(symbol)
            qty = position.get("quantity", 0)
            if qty == 0:
                return 0

            entry_price = position.get("entry_price", 0)
            mark_price = position.get("mark_price", 0)
            leverage = position.get("leverage", 1)

            if entry_price <= 0 or mark_price <= 0:
                return 0

            # Calculate profit ratio
            if qty > 0:  # LONG
                pnl_ratio = (mark_price - entry_price) / entry_price
            else:  # SHORT
                pnl_ratio = (entry_price - mark_price) / entry_price

            # ADL score = profit_ratio * leverage
            adl_score = pnl_ratio * leverage

            # Map to 1-5 quantile
            if adl_score >= 0.5:
                return 5
            elif adl_score >= 0.3:
                return 4
            elif adl_score >= 0.1:
                return 3
            elif adl_score >= 0.0:
                return 2
            else:
                return 1  # Losing position (lowest ADL priority)

        except Exception as e:
            logger.error(f"get_adl_quantile({symbol}) failed: {e}")
            return 0

    # ── Internal Order Logic ──

    async def _place_order(self, symbol: str, side: str, price: float, quantity: float) -> Dict[str, Any]:
        """Place a futures order."""
        await self._ensure_time_sync()
        await self._ensure_exchange_info()

        adj_qty = self.adjust_quantity(symbol, quantity, price=price)
        if adj_qty <= 0:
            return {"status": "failed", "message": f"Quantity too small: {quantity} → {adj_qty}"}

        params = {
            "symbol": symbol,
            "side": side,
            "quantity": str(adj_qty),
            "newOrderRespType": "RESULT",
        }

        if price > 0:
            adj_price = self.adjust_price(symbol, price)
            params["type"] = "LIMIT"
            params["timeInForce"] = "GTC"
            params["price"] = str(adj_price)
        else:
            params["type"] = "MARKET"

        try:
            result = await self._signed_post(f"{FAPI}/order", params)

            avg_price = float(result.get("avgPrice", 0)) or float(result.get("price", 0))
            executed_qty = float(result.get("executedQty", 0))
            order_status = result.get("status", "NEW")

            logger.info(f"Futures {side} {symbol}: qty={adj_qty}, price={avg_price:.2f}, status={order_status}")

            return {
                "status": "success" if order_status in ("FILLED", "NEW", "PARTIALLY_FILLED") else "failed",
                "order_id": str(result.get("orderId", "")),
                "symbol": symbol,
                "side": side.lower(),
                "price": avg_price,
                "quantity": executed_qty if executed_qty > 0 else adj_qty,
                "order_status": order_status,
            }

        except Exception as e:
            logger.error(f"Futures {side} {symbol} failed: {e}")
            return {"status": "failed", "message": str(e)}

    # ── Chart Data ──

    async def get_minute_candles(self, symbol: str, interval: str = "1", count: int = 200) -> list:
        """Fetch recent futures candles via REST API."""
        interval_map = {"1": "1m", "3": "3m", "5": "5m", "15": "15m", "30": "30m", "60": "1h"}
        binance_interval = interval_map.get(interval, f"{interval}m")

        try:
            data = await self._public_get(f"{FAPI}/klines", {
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
                    "open": float(k[1]), "high": float(k[2]),
                    "low": float(k[3]), "close": float(k[4]),
                    "volume": float(k[5]),
                })
            return candles
        except Exception as e:
            logger.error(f"get_minute_candles({symbol}) failed: {e}")
            return []

    # ── WebSocket ──

    def setup_realtime_callbacks(self):
        """Bind WebSocket callbacks."""
        if self.ws_client:
            self.ws_client.set_callbacks(
                on_tick=self._on_ws_tick,
                on_order=self._on_ws_order,
                on_balance=self._on_ws_balance,
            )

    async def _on_ws_tick(self, tick_data: Dict):
        for listener in self._tick_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    asyncio.create_task(listener(tick_data))
                else:
                    listener(tick_data)
            except Exception as e:
                logger.error(f"Tick listener error: {e}")

    async def _on_ws_order(self, order_data: Dict):
        for listener in self._order_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    asyncio.create_task(listener(order_data))
                else:
                    listener(order_data)
            except Exception as e:
                logger.error(f"Order listener error: {e}")

    async def _on_ws_balance(self, balance_data: Dict):
        for listener in self._balance_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    asyncio.create_task(listener(balance_data))
                else:
                    listener(balance_data)
            except Exception as e:
                logger.error(f"Balance listener error: {e}")
