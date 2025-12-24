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
    quantity: float | None = None
    amount: float | None = None  # target amount in KRW
    percent: float | None = None  # 0.0 to 1.0
    stop_loss: float | None = None # Percent (e.g. 3.0 for 3%)
    take_profit: float | None = None # Percent (e.g. 5.0 for 5%)

class CancelOrderRequest(BaseModel):
    order_no: str
    symbol: str
    quantity: int = 0
    origin_order_no: str = ""

class ConditionalOrderRequest(BaseModel):
    symbol: str
    condition_type: str # BUY_STOP, BUY_LIMIT, STOP_LOSS, TAKE_PROFIT, TRAILING_STOP
    trigger_price: float
    order_type: str = "buy" # Usually buy for entry
    price_type: str = "market" # market or limit
    order_price: float = 0
    mode: str # quantity, amount
    quantity: float | None = None
    amount: float | None = None
    trailing_percent: float | None = None # Required for TRAILING_STOP

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

@router.get("/orders/outstanding")
async def get_outstanding_orders(adapter: ExchangeInterface = Depends(get_exchange_adapter)):
    return await adapter.get_outstanding_orders()

@router.post("/orders/cancel")
async def cancel_order(req: CancelOrderRequest, adapter: ExchangeInterface = Depends(get_exchange_adapter)):
    result = await adapter.cancel_order(req.order_no, req.symbol, req.quantity, req.origin_order_no)
    if result.get("status") == "failed":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result


@router.post("/order/manual")
async def manual_order(
    order: ManualOrderRequest, 
    adapter: ExchangeInterface = Depends(get_exchange_adapter),
    db: Session = Depends(get_db)
):
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
        
        # Determine Safety Margin
        # Market Order: Requires margin based on Upper Limit Price (+30%), so we use conservative 0.75
        # Limit Order: Based on specific price, so we use 0.98 for fees
        margin = 0.75 if order.price_type.lower() == "market" else 0.98
        
        target_amount = current_cash * order.percent * margin
        
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

    # 3. Register Conditional Orders (Stop Loss / Take Profit)
    # Only valid for BUY orders for now (as we are setting exit conditions)
    if order.order_type.lower() == "buy" and (order.stop_loss or order.take_profit):
        try:
            from ..models.condition import ConditionalOrder, ConditionType
            
            # Use executed price if available, else usage current price logic
            # For simplicity, if it was a Market Buy, we use the current price fetched earlier or estimate
            base_price = calculated_price
            if base_price <= 0: # Market order case
                 # Ideally we should get the filled price from result, but result structure varies.
                 # We fallback to current market price for calculation base
                 price_info = await adapter.get_current_price(order.symbol)
                 base_price = price_info.get("price", 0)
            
            if base_price > 0:
                # Stop Loss
                if order.stop_loss:
                    trigger_price = base_price * (1 - (order.stop_loss / 100))
                    
                    # Validation: Stop Loss must be LOWER than current price for BUY
                    if trigger_price >= base_price:
                         print(f"Warning: Invalid Stop Loss {trigger_price} >= Base {base_price}")
                         # We could raise error, but since the main order is done, we just skip SL
                    else:
                        sl_order = ConditionalOrder(
                            symbol=order.symbol,
                            condition_type=ConditionType.STOP_LOSS,
                            trigger_price=trigger_price,
                            order_type="sell", # Exit
                            price_type="market", # Panic sell
                            quantity=quantity, # Full exit
                            status="PENDING"
                        )
                        db.add(sl_order)
                        print(f"Registered STOP_LOSS for {order.symbol} at {trigger_price}")

                # Take Profit
                if order.take_profit:
                    trigger_price = base_price * (1 + (order.take_profit / 100))
                    
                    # Validation: Take Profit must be HIGHER than current price for BUY
                    if trigger_price <= base_price:
                         print(f"Warning: Invalid Take Profit {trigger_price} <= Base {base_price}")
                    else:
                        tp_order = ConditionalOrder(
                            symbol=order.symbol,
                            condition_type=ConditionType.TAKE_PROFIT,
                            trigger_price=trigger_price,
                            order_type="sell", # Exit
                            price_type="limit", # Profit taking usually limit, but market for simplicity now
                            # For limits, we might want trigger_price or slightly lower to ensure fill
                            order_price=trigger_price, 
                            quantity=quantity,
                            status="PENDING"
                        )
                        db.add(tp_order)
                        print(f"Registered TAKE_PROFIT for {order.symbol} at {trigger_price}")
            
                db.commit()
                
        except Exception as e:
            print(f"Failed to register conditional orders: {e}")
            # We don't fail the main order if conditional registration fails, but we should log it.
        
    return result

@router.post("/order/conditional")
async def conditional_order(
    order: ConditionalOrderRequest,
    adapter: ExchangeInterface = Depends(get_exchange_adapter),
    db: Session = Depends(get_db)
):
    # Validation
    if order.trigger_price <= 0:
        raise HTTPException(status_code=400, detail="Trigger price must be > 0")

    # Calculate Quantity based on trigger price as default expectation
    quantity = 0
    calculated_price = order.order_price if order.price_type.lower() == "limit" else order.trigger_price
    if calculated_price <= 0: calculated_price = order.trigger_price # Safety

    if order.mode == "quantity":
         if not order.quantity or order.quantity <= 0:
             raise HTTPException(status_code=400, detail="Quantity required")
         quantity = order.quantity
         
    elif order.mode == "amount":
         if not order.amount or order.amount <= 0:
             raise HTTPException(status_code=400, detail="Amount required")
         
         quantity = int(order.amount // calculated_price)
    
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="Calculated quantity is 0")

    # Register to DB
    try:
        from ..models.condition import ConditionalOrder, ConditionType
        
        # Determine strict mapping
        allowed_buy = ["BUY_STOP", "BUY_LIMIT"]
        allowed_sell = ["STOP_LOSS", "TAKE_PROFIT", "TRAILING_STOP"] # Stop Loss = Sell Stop, Take Profit = Sell Limit

        if order.order_type.lower() == "buy":
             if order.condition_type not in allowed_buy:
                  raise HTTPException(status_code=400, detail=f"Invalid condition {order.condition_type} for BUY order")
        elif order.order_type.lower() == "sell":
             if order.condition_type not in allowed_sell:
                  raise HTTPException(status_code=400, detail=f"Invalid condition {order.condition_type} for SELL order")
        else:
             raise HTTPException(status_code=400, detail="Invalid order type")
             
        # Validation for Trailing Stop
        if order.condition_type == "TRAILING_STOP":
            if not order.trailing_percent or order.trailing_percent <= 0:
                raise HTTPException(status_code=400, detail="Trailing percent is required for TRAILING_STOP")
                
        cond_order = ConditionalOrder(
            symbol=order.symbol,
            condition_type=order.condition_type,
            trigger_price=order.trigger_price, # Initial activation price (optional for TS? usually immediate or specific level)
            order_type=order.order_type,
            price_type=order.price_type,
            order_price=order.order_price,
            quantity=quantity,
            status="PENDING",
            # Trailing Stop specific
            trailing_percent=order.trailing_percent if order.condition_type == "TRAILING_STOP" else None,
            highest_price=order.trigger_price if order.condition_type == "TRAILING_STOP" else None # Initialize High Water Mark
        )
        db.add(cond_order)
        db.commit()
        db.refresh(cond_order)
        
        return {
            "status": "success", 
            "message": f"Watch Order Registered: {order.order_type.upper()} {order.condition_type}",
            "id": cond_order.id
        }
        
    except Exception as e:
        print(f"Error registering conditional order: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
