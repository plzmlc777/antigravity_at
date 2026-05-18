"""
MCP server tool handlers — thin wrappers around BinanceFuturesAdapter.

Each handler:
  1. Resolves the active adapter (paper for Tier 2, real for Tier 3 if gated)
  2. Calls the underlying adapter method
  3. Returns a JSON-serializable dict / list

Tier 1 (read-only): always uses paper-configured adapter (read endpoints
identical between testnet and live; we use testnet to keep blast radius zero).
Tier 2 (paper-write): always force_paper=True (testnet only).
Tier 3 (real-write): requires risk_check.check_real_trade_allowed() PASS first.
"""
import logging
from typing import Any, Dict, List

from .auth import load_account, make_adapter, resolve_account_id
from .risk_check import check_real_trade_allowed

logger = logging.getLogger(__name__)


def _adapter(force_paper: bool):
    account = load_account(resolve_account_id())
    return make_adapter(account, force_paper=force_paper)


# ===== Tier 1 — Read-only =====

async def get_funding_rate(symbol: str) -> Dict[str, Any]:
    adapter = _adapter(force_paper=True)
    rate = await adapter.get_funding_rate(symbol)
    return {"symbol": symbol, "funding_rate": rate}


async def get_ohlcv(symbol: str, interval: str = "1h", count: int = 200) -> List[Dict[str, Any]]:
    adapter = _adapter(force_paper=True)
    return await adapter.get_minute_candles(symbol=symbol, interval=interval, count=count)


async def get_position(symbol: str) -> Dict[str, Any]:
    adapter = _adapter(force_paper=True)
    return await adapter.get_position(symbol)


async def get_balance() -> Dict[str, Any]:
    adapter = _adapter(force_paper=True)
    return await adapter.get_balance()


async def get_outstanding_orders() -> List[Dict[str, Any]]:
    adapter = _adapter(force_paper=True)
    return await adapter.get_outstanding_orders()


async def get_current_price(symbol: str) -> Dict[str, Any]:
    adapter = _adapter(force_paper=True)
    return await adapter.get_current_price(symbol)


async def get_adl_quantile(symbol: str) -> Dict[str, Any]:
    adapter = _adapter(force_paper=True)
    quantile = await adapter.get_adl_quantile(symbol)
    return {"symbol": symbol, "adl_quantile": quantile}


# ===== Tier 2 — Paper-write (testnet only) =====

async def paper_place_long_order(symbol: str, price: float, quantity: float) -> Dict[str, Any]:
    adapter = _adapter(force_paper=True)
    logger.info("paper LONG: symbol=%s price=%s qty=%s", symbol, price, quantity)
    return await adapter.place_buy_order(symbol=symbol, price=price, quantity=quantity)


async def paper_place_short_order(symbol: str, price: float, quantity: float) -> Dict[str, Any]:
    adapter = _adapter(force_paper=True)
    logger.info("paper SHORT: symbol=%s price=%s qty=%s", symbol, price, quantity)
    return await adapter.place_short_order(symbol=symbol, price=price, quantity=quantity)


async def paper_close_position(symbol: str) -> Dict[str, Any]:
    adapter = _adapter(force_paper=True)
    logger.info("paper CLOSE: symbol=%s", symbol)
    return await adapter.close_position(symbol)


async def paper_cancel_order(order_id: str, symbol: str) -> Dict[str, Any]:
    adapter = _adapter(force_paper=True)
    logger.info("paper CANCEL: order_id=%s symbol=%s", order_id, symbol)
    return await adapter.cancel_order(order_id=order_id, symbol=symbol)


# ===== Tier 3 — Real-write (env-gated, risk-manager VETO required) =====

async def real_place_long_order(symbol: str, price: float, quantity: float) -> Dict[str, Any]:
    check_real_trade_allowed("real_place_long_order", {"symbol": symbol, "price": price, "quantity": quantity})
    adapter = _adapter(force_paper=False)
    logger.warning("REAL LONG: symbol=%s price=%s qty=%s", symbol, price, quantity)
    return await adapter.place_buy_order(symbol=symbol, price=price, quantity=quantity)


async def real_place_short_order(symbol: str, price: float, quantity: float) -> Dict[str, Any]:
    check_real_trade_allowed("real_place_short_order", {"symbol": symbol, "price": price, "quantity": quantity})
    adapter = _adapter(force_paper=False)
    logger.warning("REAL SHORT: symbol=%s price=%s qty=%s", symbol, price, quantity)
    return await adapter.place_short_order(symbol=symbol, price=price, quantity=quantity)


async def real_close_position(symbol: str) -> Dict[str, Any]:
    check_real_trade_allowed("real_close_position", {"symbol": symbol})
    adapter = _adapter(force_paper=False)
    logger.warning("REAL CLOSE: symbol=%s", symbol)
    return await adapter.close_position(symbol)


async def real_cancel_order(order_id: str, symbol: str) -> Dict[str, Any]:
    check_real_trade_allowed("real_cancel_order", {"order_id": order_id, "symbol": symbol})
    adapter = _adapter(force_paper=False)
    logger.warning("REAL CANCEL: order_id=%s symbol=%s", order_id, symbol)
    return await adapter.cancel_order(order_id=order_id, symbol=symbol)
