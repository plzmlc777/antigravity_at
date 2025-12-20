from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
from ..adapters.kiwoom_mock import KiwoomMockAdapter
from ..adapters.kiwoom_real import KiwoomRealAdapter
from ..core.exchange_interface import ExchangeInterface
from ..core.config import settings
from pydantic import BaseModel

router = APIRouter()

# Dependency Injection for Exchange Adapter
def get_exchange_adapter() -> ExchangeInterface:
    if settings.TRADING_MODE.upper() == "REAL":
        return KiwoomRealAdapter()
    return KiwoomMockAdapter()

class OrderRequest(BaseModel):
    symbol: str
    price: float
    quantity: float

@router.get("/status")
async def get_status(adapter: ExchangeInterface = Depends(get_exchange_adapter)):
    return {"exchange": adapter.get_name(), "status": "online"}

@router.get("/price/{symbol}")
async def get_price(symbol: str, adapter: ExchangeInterface = Depends(get_exchange_adapter)):
    # Returns { "symbol": "...", "price": 100, "name": "Samsung" }
    return await adapter.get_current_price(symbol)

@router.get("/balance")
async def get_balance(adapter: ExchangeInterface = Depends(get_exchange_adapter)):
    return await adapter.get_balance()

@router.post("/order/buy")
async def buy_order(order: OrderRequest, adapter: ExchangeInterface = Depends(get_exchange_adapter)):
    result = await adapter.place_buy_order(order.symbol, order.price, order.quantity)
    if result.get("status") == "failed":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result

@router.post("/order/sell")
async def sell_order(order: OrderRequest, adapter: ExchangeInterface = Depends(get_exchange_adapter)):
    result = await adapter.place_sell_order(order.symbol, order.price, order.quantity)
    if result.get("status") == "failed":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result
