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

    async def place_reduce_only_limit(self, symbol: str, side: str,
                                      price: float, quantity: float
                                      ) -> Dict[str, Any]:
        """**호가에 얹어 두는** 지정가 청산 주문. 익절 전용.

        왜 따로 두는가 (2026-08-22)
            RSI 전략의 엣지는 **익절이 지정가로 채워지는 것**에 달려 있다.
            백테스트가 익절가 정확 체결 · 메이커 2bp · 슬리피지 0 을 전제한다.
            조건부 주문(`place_algo_stop`)은 트리거 후 **시장가**라 테이커에
            슬리피지가 붙어 전제가 깨진다. 그래서 평범한 LIMIT GTC 를 미리
            얹어 둔다 — 가격에 닿으면 우리가 메이커다.

        ⚠ `reduceOnly` 는 **필수**다. 없으면 포지션이 이미 닫힌 뒤 남은
          지정가가 **반대 포지션을 새로 연다**. 거래소가 막아주는 유일한 장치다.

        ⚠ 체결 확인을 하지 않는다. 이 주문은 **안 채워지는 게 정상**이다.
          `_place_order` 는 즉시 체결을 전제해 avgPrice=0 이면 오류를 찍는다.
        """
        await self._ensure_time_sync()
        await self._ensure_exchange_info()
        adj_qty = self.adjust_quantity(symbol, quantity, price=price)
        if adj_qty <= 0:
            return {"status": "failed",
                    "message": f"수량이 최소단위 미만 — {quantity} → {adj_qty}"}
        params = {
            "symbol": symbol,
            "side": side,
            "type": "LIMIT",
            "timeInForce": "GTC",
            "price": str(self.adjust_price(symbol, price)),
            "quantity": str(adj_qty),
            "reduceOnly": "true",
            "newOrderRespType": "RESULT",
        }
        try:
            r = await self._signed_post(f"{FAPI}/order", params)
            logger.info("%s 익절 지정가 등록 — %s %s @ %s (id=%s)",
                        symbol, side, adj_qty, params["price"], r.get("orderId"))
            return {"status": "success", "order_id": str(r.get("orderId", "")),
                    "symbol": symbol, "side": side.lower(),
                    "price": float(params["price"]), "quantity": adj_qty,
                    "order_status": r.get("status", "NEW")}
        except Exception as e:
            logger.error("%s 익절 지정가 등록 실패: %s", symbol, e)
            return {"status": "failed", "message": str(e)}

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

            px, qty_filled = await self._confirm_fill(
                symbol, str(result.get("orderId", "")),
                float(result.get("avgPrice", 0)),
                float(result.get("executedQty", 0)))
            if qty_filled <= 0:
                # 체결수량 0을 요청수량으로 올려보낸다. reduceOnly 시장가 청산은
                # 거의 전량 체결되고 위에서 포지션 수량을 이미 확인했으므로 실용적
                # 근사지만, 0이 "정말 미체결"인 경우 상위가 체결로 기록한다.
                logger.warning(f"{symbol}: 청산 체결수량을 확인하지 못해 요청수량 "
                               f"{adj_qty} 로 보고한다 — 미체결이면 기록이 부정확해진다")
            return {
                "status": "success",
                "order_id": str(result.get("orderId", "")),
                "symbol": symbol,
                "side": side.lower(),
                # or-audit: safe — 바로 위에서 0을 경고로 드러낸다
                "quantity": qty_filled or adj_qty,
                "price": px,
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

    async def _confirm_fill(self, symbol: str, order_id: str,
                            avg_price: float, executed_qty: float) -> tuple:
        """avgPrice가 0으로 온 주문의 실제 체결가·수량을 재조회로 확정한다.

        newOrderRespType=RESULT를 줘도 MARKET 주문이 아직 NEW 상태면 응답의
        avgPrice가 "0"으로 온다. 그 0을 그대로 올려보내면 상위(live_context)가
        조용히 이론가로 대체해 손익·현금 회계가 어긋난다 — 실계좌 39건 중 23건이
        이렇게 System-2 바 종가로 기록됐다(2026-08-08 확인). 여기서 확정해
        내보내면 모든 호출자가 정확한 값을 받는다.

        짧게 두 번만 재시도하고, 끝내 못 구하면 받은 값을 그대로 돌려준다
        (상위에서 0을 보고 판단할 수 있게 — 조용한 대체는 하지 않는다).
        """
        if avg_price > 0 or not order_id:
            return (avg_price, executed_qty)
        for delay in (0.0, 0.3):
            if delay:
                await asyncio.sleep(delay)
            try:
                o = await self._signed_get(f"{FAPI}/order",
                                           {"symbol": symbol, "orderId": order_id})
                px = float(o.get("avgPrice") or 0)
                qty = float(o.get("executedQty") or 0)
                if px > 0:
                    logger.info(f"{symbol} order {order_id}: avgPrice 재조회로 확정 "
                                f"px={px} qty={qty} status={o.get('status')}")
                    # or-audit: safe — 재조회에서 px>0 인데 qty=0 이면 응답 시점
                    # 차이일 뿐이므로 원 응답의 executedQty 를 쓴다. 둘 다 같은
                    # '체결수량' 후보이고, 최종 0 은 호출측이 경고로 드러낸다.
                    return (px, qty or executed_qty)
            except Exception as e:
                logger.warning(f"{symbol} order {order_id} 재조회 실패: {e}")
                break
        logger.error(f"{symbol} order {order_id}: 체결가를 확정하지 못했다 (avgPrice=0) "
                     f"— 상위에서 이론가로 대체되면 손익이 부정확해진다")
        return (avg_price, executed_qty)

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
            avg_price, executed_qty = await self._confirm_fill(
                symbol, str(result.get("orderId", "")), avg_price, executed_qty)

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

    async def get_minute_candles(self, symbol: str, interval: str = "1", count: int = 200, interval_minutes: int = None) -> list:
        """Fetch recent futures candles via REST API."""
        if interval_minutes is not None:
            interval = str(interval_minutes)
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
                from datetime import datetime, timezone, timedelta
                KST = timezone(timedelta(hours=9))
                ts = datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc).astimezone(KST)
                candles.append({
                    "timestamp": ts.isoformat(),
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

    async def start_realtime(self, symbols: list = None):
        """Start Binance Futures WebSocket and subscribe to symbols."""
        from .binance_websocket import BinanceWebSocket

        if not self.ws_client:
            self.ws_client = BinanceWebSocket(
                api_key=self.api_key,
                secret_key=self.secret_key,
                api_url=self.api_url,
                is_testnet=self.is_testnet,
                is_futures=True,
            )
            self.setup_realtime_callbacks()

        if symbols:
            await self.ws_client.subscribe_symbols(symbols)

        if not self.ws_client.is_running:
            await self.ws_client.connect()
            logger.info(f"Binance Futures WebSocket started for {symbols}")

    async def stop_realtime(self):
        """Stop Binance Futures WebSocket."""
        if self.ws_client:
            await self.ws_client.disconnect()
            logger.info("Binance Futures WebSocket stopped")

    async def _on_ws_tick(self, tick_data: Dict):
        for listener in self._tick_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    asyncio.create_task(listener(tick_data))
                else:
                    listener(tick_data)
            except Exception as e:
                logger.error(f"Tick listener error: {e}")

    # ══════════════════════════════════════════════════════════════
    #  조건부 주문 (Algo) — 거래소가 감시한다
    # ══════════════════════════════════════════════════════════════
    #
    # ⚠ 왜 필요한가 (2026-08-20)
    #   지금까지 손절·익절을 `pending_orders.py` 가 **클라이언트에서** 감시했다.
    #   봉이 닫혀야 평가하므로(live_engine:574, `if closed_candle:` 안), 1시간봉
    #   세션이면 최대 1시간을 손절선 아래에서 방치한다. 엔진이 죽으면 보호가 0 이다.
    #   실제로 엔진·거래소 장부 불일치로 Day-30 청산이 안 된 사고가 있었다.
    #
    #   거래소 조건부 주문은 **약 10ms 마다** 감시한다(공식 문서). 엔진 상태와
    #   무관하게 작동한다.
    #
    # ⚠ 경로가 바뀌었다 — 2025-12-09
    #   USDⓈ-M 조건부 주문이 Algo 서비스로 이관됐다. STOP_MARKET /
    #   TAKE_PROFIT_MARKET / STOP / TAKE_PROFIT / TRAILING_STOP_MARKET 를
    #   `POST /fapi/v1/order` 로 보내면 **-4120 STOP_ORDER_SWITCH_ALGO** 로 막힌다.
    #   반드시 `/fapi/v1/algoOrder` 를 써야 한다.
    #
    # ⚠ 이관과 함께 바뀐 동작
    #   · 트리거 전에는 증거금 검사를 하지 않는다
    #   · 미체결 조건부 주문은 **수정 불가** — 취소 후 재등록해야 한다
    #   · GTE_GTC 가 반대편 미체결 주문이 아니라 **포지션에만** 의존한다

    async def place_algo_stop(self, symbol: str, side: str, trigger_price: float,
                              *, limit_price: float = 0.0,
                              take_profit: bool = False,
                              close_position: bool = True,
                              quantity: float = 0.0,
                              working_type: str = "CONTRACT_PRICE",
                              price_protect: bool = False) -> Dict[str, Any]:
        """조건부 주문을 **거래소에** 건다.

        side        : 청산 방향. 롱 포지션을 닫으려면 "SELL".
        limit_price : 0 이면 STOP_MARKET / TAKE_PROFIT_MARKET (체결 보장, 가격 미보장).
                      >0 이면 STOP / TAKE_PROFIT (가격 보장, **체결 미보장**).
        close_position: True 면 전량 청산. quantity·reduceOnly 와 함께 못 쓴다.

        ⚠ closePosition=true 는 **포지션이 있어야만** 등록된다 (실계좌 확인)
            내부적으로 GTE_GTC(포지션 종료 전용 TIF)를 쓰므로, 포지션 없이
            걸면 -4509 "TIF GTE can only be used with open positions" 로 막힌다.
            거래소가 **고아 주문을 원천 차단**하는 설계다 — 포지션이 닫힌 뒤
            남은 주문이 다음 진입을 엉뚱하게 청산하는 사고를 막아준다.
            따라서 진입 **직후**에만 걸 수 있고, 사전에 미리 걸어둘 수 없다.

        ⚠ 포지션 없이 시험하려면 close_position=False + quantity 를 쓴다
            reduceOnly=true 여도 등록된다(2026-08-20 계좌 8 실측).
        price_protect : True 면 표시가·계약가 괴리가 임계를 넘을 때 **체결을 막는다**.
                        손절에 켜면 급락에 안 나갈 수 있다 — 기본 False.
        """
        await self._ensure_time_sync()
        await self._ensure_exchange_info()
        kind = "TAKE_PROFIT" if take_profit else "STOP"
        params: Dict[str, Any] = {
            # ⚠ algoType 은 **필수**다. 안 보내면 -1102 로 막힌다
            #   (2026-08-20 실계좌 시험에서 확인). 허용값은 CONDITIONAL 하나.
            "algoType": "CONDITIONAL",
            "symbol": symbol,
            "side": side,
            "type": kind if limit_price > 0 else f"{kind}_MARKET",
            "triggerPrice": str(self.adjust_price(symbol, trigger_price)),
            "workingType": working_type,
            "priceProtect": "true" if price_protect else "false",
            "newOrderRespType": "RESULT",
        }
        if limit_price > 0:
            params["price"] = str(self.adjust_price(symbol, limit_price))
            params["timeInForce"] = "GTC"
        if close_position:
            params["closePosition"] = "true"
        else:
            # ⚠ 수량 보정 기준은 **현재가**다. 트리거 가격을 넘기면 안 된다 —
            #   손절 트리거는 현재가보다 한참 아래라 최소 명목금액 검사에서
            #   수량이 0 으로 잘린다(2026-08-20 실계좌 시험에서 발생).
            ref_px = trigger_price
            try:
                cp = await self.get_current_price(symbol)
                v = float(cp.get("price", cp.get("current_price", 0)) or 0)
                if v > 0:
                    ref_px = v
            except Exception:
                pass
            adj = self.adjust_quantity(symbol, quantity, price=ref_px)
            if adj <= 0:
                return {"status": "failed", "message": f"수량 부족 {quantity} → {adj}"}
            params["quantity"] = str(adj)
            params["reduceOnly"] = "true"
        try:
            r = await self._signed_post(f"{FAPI}/algoOrder", params)
            logger.info("Algo %s %s %s trigger=%s → id=%s",
                        params["type"], side, symbol, params["triggerPrice"],
                        r.get("algoId") or r.get("orderId"))
            return {"status": "success", "raw": r,
                    "algo_id": str(r.get("algoId") or r.get("orderId") or "")}
        except Exception as exc:
            logger.error("Algo 주문 실패 %s %s: %s", symbol, params["type"], exc)
            return {"status": "failed", "message": str(exc)}

    async def cancel_algo_order(self, symbol: str, algo_id: str) -> Dict[str, Any]:
        """조건부 주문 취소. 반대쪽이 체결되면 **반드시** 불러야 한다 —
        안 그러면 포지션 없이 주문만 남아 반대 포지션이 열린다."""
        try:
            r = await self._signed_delete(f"{FAPI}/algoOrder",
                                          {"symbol": symbol, "algoId": algo_id})
            return {"status": "success", "raw": r}
        except Exception as exc:
            logger.error("Algo 취소 실패 %s %s: %s", symbol, algo_id, exc)
            return {"status": "failed", "message": str(exc)}

    async def cancel_all_algo_orders(self, symbol: str) -> Dict[str, Any]:
        """해당 종목의 조건부 주문 전부 취소 (고아 주문 정리용)."""
        try:
            r = await self._signed_delete(f"{FAPI}/algoOpenOrders",
                                          {"symbol": symbol})
            return {"status": "success", "raw": r}
        except Exception as exc:
            return {"status": "failed", "message": str(exc)}

    async def get_open_algo_orders(self, symbol: str = "") -> list:
        """미체결 조건부 주문 조회. 엔진 장부와 거래소 장부를 맞출 때 쓴다."""
        try:
            params = {"symbol": symbol} if symbol else {}
            r = await self._signed_get(f"{FAPI}/openAlgoOrders", params)
            return r if isinstance(r, list) else r.get("orders", [])
        except Exception as exc:
            logger.error("Algo 조회 실패: %s", exc)
            return []

    async def get_order_executions(self, order_no: str = "", symbol: str = "") -> list:
        """Get recent trade/fill history from Binance Futures."""
        await self._ensure_time_sync()
        try:
            params = {"limit": 50}
            if symbol:
                params["symbol"] = symbol
            trades = await self._signed_get(f"{FAPI}/userTrades", params)
            results = []
            for t in trades:
                results.append({
                    "order_no": str(t.get("orderId", "")),
                    "symbol": t.get("symbol", ""),
                    "side": t.get("side", ""),
                    "filled_price": float(t.get("price", 0)),
                    "filled_qty": float(t.get("qty", 0)),
                    "commission": float(t.get("commission", 0)),
                    "realized_pnl": float(t.get("realizedPnl", 0)),
                    "time": t.get("time", 0),
                })
            return results
        except Exception as e:
            logger.error(f"get_order_executions() failed: {e}")
            return []

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
