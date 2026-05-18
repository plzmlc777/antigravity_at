"""
Kiwoom MCP server tool handlers — thin wrappers around KiwoomRealAdapter.

Tier 1 (read-only): force_virtual=True 모의 서버로 시세 조회 (실거래 영향 0)
Tier 2 (paper-write): force_virtual=True 모의투자 주문
Tier 3 (real-write): risk_check.check_real_trade_allowed() PASS 후만 force_virtual=False
"""
import logging
from typing import Any, Dict, List

from .auth import load_account, make_adapter, resolve_account_id
from .risk_check import check_real_trade_allowed

logger = logging.getLogger(__name__)


def _adapter(force_virtual: bool):
    account = load_account(resolve_account_id())
    return make_adapter(account, force_virtual=force_virtual)


# ===== Tier 1 — Read-only =====

async def get_kr_current_price(symbol: str) -> Dict[str, Any]:
    adapter = _adapter(force_virtual=True)
    return await adapter.get_current_price(symbol)


async def get_kr_minute_candles(symbol: str, interval_minutes: int = 1) -> List[Dict[str, Any]]:
    adapter = _adapter(force_virtual=True)
    return await adapter.get_minute_candles(symbol=symbol, interval_minutes=interval_minutes)


async def get_kr_daily_candles(symbol: str, base_dt: str = None) -> List[Dict[str, Any]]:
    adapter = _adapter(force_virtual=True)
    return await adapter.get_daily_candles(symbol=symbol, base_dt=base_dt)


async def get_kr_candles(symbol: str, interval: str = "1d", days: int = 30, limit: int = 1000) -> List[Dict[str, Any]]:
    adapter = _adapter(force_virtual=True)
    return await adapter.get_candles(symbol=symbol, interval=interval, days=days, limit=limit)


async def get_kr_balance() -> Dict[str, Any]:
    adapter = _adapter(force_virtual=True)
    return await adapter.get_balance()


async def get_kr_outstanding_orders() -> List[Dict[str, Any]]:
    adapter = _adapter(force_virtual=True)
    return await adapter.get_outstanding_orders()


async def get_kr_order_executions(order_no: str = "", symbol: str = "") -> List[Dict[str, Any]]:
    adapter = _adapter(force_virtual=True)
    return await adapter.get_order_executions(order_no=order_no, symbol=symbol)


# ===== Tier 2 — Paper-write (모의투자 only) =====

async def paper_buy_stock(symbol: str, price: float, quantity: int) -> Dict[str, Any]:
    adapter = _adapter(force_virtual=True)
    logger.info("paper KR BUY: symbol=%s price=%s qty=%s", symbol, price, quantity)
    return await adapter.place_buy_order(symbol=symbol, price=price, quantity=quantity)


async def paper_sell_stock(symbol: str, price: float, quantity: int) -> Dict[str, Any]:
    adapter = _adapter(force_virtual=True)
    logger.info("paper KR SELL: symbol=%s price=%s qty=%s", symbol, price, quantity)
    return await adapter.place_sell_order(symbol=symbol, price=price, quantity=quantity)


async def paper_cancel_kr_order(order_id: str, symbol: str, quantity: int, origin_order_id: str = "") -> Dict[str, Any]:
    adapter = _adapter(force_virtual=True)
    logger.info("paper KR CANCEL: order_id=%s symbol=%s qty=%s", order_id, symbol, quantity)
    return await adapter.cancel_order(order_id=order_id, symbol=symbol, quantity=quantity, origin_order_id=origin_order_id)


# ===== Tier 3 — Real-write (env-gated, risk-manager VETO required) =====

async def real_buy_stock(symbol: str, price: float, quantity: int) -> Dict[str, Any]:
    check_real_trade_allowed("real_buy_stock", {"symbol": symbol, "price": price, "quantity": quantity})
    adapter = _adapter(force_virtual=False)
    logger.warning("REAL KR BUY: symbol=%s price=%s qty=%s", symbol, price, quantity)
    return await adapter.place_buy_order(symbol=symbol, price=price, quantity=quantity)


async def real_sell_stock(symbol: str, price: float, quantity: int) -> Dict[str, Any]:
    check_real_trade_allowed("real_sell_stock", {"symbol": symbol, "price": price, "quantity": quantity})
    adapter = _adapter(force_virtual=False)
    logger.warning("REAL KR SELL: symbol=%s price=%s qty=%s", symbol, price, quantity)
    return await adapter.place_sell_order(symbol=symbol, price=price, quantity=quantity)


async def real_cancel_kr_order(order_id: str, symbol: str, quantity: int, origin_order_id: str = "") -> Dict[str, Any]:
    check_real_trade_allowed("real_cancel_kr_order", {"order_id": order_id, "symbol": symbol, "quantity": quantity})
    adapter = _adapter(force_virtual=False)
    logger.warning("REAL KR CANCEL: order_id=%s symbol=%s qty=%s", order_id, symbol, quantity)
    return await adapter.cancel_order(order_id=order_id, symbol=symbol, quantity=quantity, origin_order_id=origin_order_id)
