from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
from ..adapters.kiwoom_mock import KiwoomMockAdapter
from ..adapters.kiwoom_real import KiwoomRealAdapter
from ..core.exchange_interface import ExchangeInterface
from ..core.config import settings
from ..db.session import get_db
from sqlalchemy.orm import Session
from pydantic import BaseModel

router = APIRouter()

# Dependency Injection for Exchange Adapter
# Dependency Injection for Exchange Adapter
def get_exchange_adapter(db: Session = Depends(get_db)) -> ExchangeInterface:
    if settings.TRADING_MODE.upper() == "REAL":
        # Fetch active account for current user/system
        # Note: In a multi-user system, we'd need current_user here. 
        # But since Trading Bot often runs in background, we might need a 'System User' or just the first active account.
        # For this MVP, we pick the first active account found in DB.
        
        from ..models.account import ExchangeAccount
        from ..core import security
        
        active_account = db.query(ExchangeAccount).filter(ExchangeAccount.is_active == True).first()
        
        if active_account:
            try:
                decrypted_app = security.decrypt_key(active_account.encrypted_access_key)
                decrypted_secret = security.decrypt_key(active_account.encrypted_secret_key)
                return KiwoomRealAdapter(
                    app_key=decrypted_app,
                    secret_key=decrypted_secret,
                    account_no=active_account.account_number,
                    account_name=active_account.account_name
                )
            except Exception as e:
                # Log error and fallback (or fail)
                print(f"Error decrypting keys: {e}")
                pass
                
        # Fallback to .env if DB lookup fails or no active account
        return KiwoomRealAdapter()
        
    return KiwoomMockAdapter()

class OrderRequest(BaseModel):
    symbol: str
    price: float
    quantity: float

class ManualOrderRequest(BaseModel):
    symbol: str
    order_type: str  # "buy" or "sell"
    price_type: str = "limit" # "limit" or "market"
    price: float = 0 # Optional for market
    mode: str  # "quantity", "amount", "percent_cash", "percent_holding"
    quantity: float = None
    amount: float = None  # target amount in KRW
    percent: float = None  # 0.0 to 1.0

@router.get("/status")
async def get_status(adapter: ExchangeInterface = Depends(get_exchange_adapter)):
    return {
        "exchange": adapter.get_name(), 
        "status": "online",
        "mode": settings.TRADING_MODE,
        "account_name": adapter.get_account_name()
    }

class SystemModeRequest(BaseModel):
    mode: str # REAL or MOCK

@router.post("/system/mode")
async def set_system_mode(request: SystemModeRequest):
    try:
        settings.set_mode(request.mode)
        return {"status": "success", "mode": settings.TRADING_MODE}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

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

@router.post("/order/manual")
async def manual_order(order: ManualOrderRequest, adapter: ExchangeInterface = Depends(get_exchange_adapter)):
    quantity = 0
    calculated_price = order.price

    # If Market Order, disable price validation and set price to 0 for execution
    # but we might need current price for Amount/Percent calculation
    if order.price_type.lower() == "market":
        calculated_price = 0
        current_price_info = await adapter.get_current_price(order.symbol)
        current_price = current_price_info.get("price", 0)
        if current_price <= 0:
             raise HTTPException(status_code=400, detail="Failed to fetch current price for Market Order")
    else:
        # Limit Order
        current_price = order.price # Use input price for calculation
    
    # 1. Calculate Quantity based on Mode
    if order.mode == "quantity":
        if order.quantity is None or order.quantity <= 0:
             raise HTTPException(status_code=400, detail="Quantity is required for 'quantity' mode")
        quantity = order.quantity
        
    elif order.mode == "amount":
        if order.amount is None or order.amount <= 0:
            raise HTTPException(status_code=400, detail="Amount is required for 'amount' mode")
        
        calc_basis_price = current_price if order.price_type.lower() == "market" else order.price
        
        if calc_basis_price <= 0:
             raise HTTPException(status_code=400, detail="Price must be > 0 for calculation")
             
        quantity = int(order.amount // calc_basis_price)
        
    elif order.mode == "percent_cash":
        # Only valid for BUY
        if order.order_type.lower() != "buy":
             raise HTTPException(status_code=400, detail="'percent_cash' is only valid for BUY orders")
             
        if order.percent is None or not (0 < order.percent <= 1):
             raise HTTPException(status_code=400, detail="Percent must be between 0 and 1")
             
        balance_info = await adapter.get_balance()
        cash_data = balance_info.get("cash", {})
        current_cash = cash_data.get("KRW", 0)
        
        target_amount = current_cash * order.percent
        
        calc_basis_price = current_price if order.price_type.lower() == "market" else order.price
        if calc_basis_price <= 0:
             raise HTTPException(status_code=400, detail="Price must be > 0 for calculation")
             
        quantity = int(target_amount // calc_basis_price)
        
    elif order.mode == "percent_holding":
        # Only valid for SELL
        if order.order_type.lower() != "sell":
             raise HTTPException(status_code=400, detail="'percent_holding' is only valid for SELL orders")

        if order.percent is None or not (0 < order.percent <= 1):
             raise HTTPException(status_code=400, detail="Percent must be between 0 and 1")
             
        balance_info = await adapter.get_balance()
        holdings = balance_info.get("holdings", {})
        current_qty = holdings.get(order.symbol, 0)
        
        quantity = int(current_qty * order.percent)
        
    else:
        raise HTTPException(status_code=400, detail=f"Unknown mode: {order.mode}")

    if quantity <= 0:
        raise HTTPException(status_code=400, detail="Calculated quantity is 0 or invalid")

    # 2. Execute Order
    if order.order_type.lower() == "buy":
        result = await adapter.place_buy_order(order.symbol, calculated_price, quantity)
    elif order.order_type.lower() == "sell":
        result = await adapter.place_sell_order(order.symbol, calculated_price, quantity)
    else:
        raise HTTPException(status_code=400, detail="Invalid order type")

    if result.get("status") == "failed":
        raise HTTPException(status_code=400, detail=result.get("message"))
        
    return result

@router.post("/auto/start")
async def start_auto_trading(
    config: Dict[str, Any], 
    adapter: ExchangeInterface = Depends(get_exchange_adapter)
):
    """
    Start a new trading bot.
    config needs: symbol, strategy, interval(seconds), amount(KRW), strategy_config
    """
    from ..core.bot_manager import bot_manager
    
    # Validation
    if 'symbol' not in config:
        raise HTTPException(status_code=400, detail="Symbol is required")
    if 'strategy' not in config:
        raise HTTPException(status_code=400, detail="Strategy is required")
        
    try:
        bot_id = bot_manager.start_bot(config)
        return {"status": "success", "message": "Bot started", "bot_id": bot_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/auto/stop/{bot_id}")
async def stop_auto_trading(bot_id: str):
    from ..core.bot_manager import bot_manager
    bot_manager.stop_bot(bot_id)
    return {"status": "success", "message": f"Bot {bot_id} stopped"}

@router.delete("/auto/{bot_id}")
async def delete_bot(bot_id: str):
    from ..core.bot_manager import bot_manager
    bot_manager.remove_bot(bot_id)
    return {"status": "success", "message": f"Bot {bot_id} removed"}

@router.get("/auto/status")
async def get_auto_trading_status():
    from ..core.bot_manager import bot_manager
    return bot_manager.get_status()
