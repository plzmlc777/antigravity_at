from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
from ..adapters.kiwoom_real import KiwoomRealAdapter
from ..core.exchange_interface import ExchangeInterface
from ..core.config import settings
from ..core.trading_env import TradingEnvironment, get_api_url, env_from_string
from ..db.session import get_db
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from ..core.waterfall_engine import fetch_visualization_feeds
from .auth import get_current_user
from ..models.user import User
from ..core.user_context import UserAccountContext, get_user_context

router = APIRouter()

# Dependency Injection for Exchange Adapter
def get_exchange_adapter_for_user(db: Session, user_id: int) -> ExchangeInterface:
    """Get exchange adapter for a specific user's active account"""
    from ..core.account_cache import AccountCache
    from ..models.account import ExchangeAccount
    from ..core import security

    cache = AccountCache.get_instance()

    # Check cache first
    cached_config = cache.get_active_account_config(user_id)

    if cached_config:
        env = env_from_string(cached_config.get('environment', 'real'))
        api_url = get_api_url(env)
        is_virtual = env == TradingEnvironment.VIRTUAL

        return KiwoomRealAdapter(
            app_key=cached_config['app_key'],
            secret_key=cached_config['secret_key'],
            account_no=cached_config['account_no'],
            account_name=cached_config['account_name'],
            api_url=api_url,
            is_virtual=is_virtual
        )

    # Fetch active account for this user from DB
    active_account = db.query(ExchangeAccount).filter(
        ExchangeAccount.user_id == user_id,
        ExchangeAccount.is_active == True
    ).first()

    if active_account:
        try:
            decrypted_app = security.decrypt_key(active_account.encrypted_access_key)
            decrypted_secret = security.decrypt_key(active_account.encrypted_secret_key)

            config = {
                'app_key': decrypted_app,
                'secret_key': decrypted_secret,
                'account_no': active_account.account_number,
                'account_name': active_account.account_name,
                'environment': active_account.environment or TradingEnvironment.REAL.value
            }
            cache.set_active_account_config(user_id, config)

            return KiwoomRealAdapter(
                app_key=decrypted_app,
                secret_key=decrypted_secret,
                account_no=active_account.account_number,
                account_name=active_account.account_name,
                api_url=active_account.api_url,
                is_virtual=active_account.is_virtual
            )
        except Exception as e:
            print(f"Error decrypting keys: {e}")
            pass

    # Fallback to .env
    return KiwoomRealAdapter()


def get_exchange_adapter(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> ExchangeInterface:
    """Get exchange adapter for current user's active account"""
    return get_exchange_adapter_for_user(db, current_user.id)

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
async def get_status(ctx: UserAccountContext = Depends(get_user_context)):
    adapter = ctx.get_exchange_adapter()

    return {
        "exchange": adapter.get_name(),
        "status": "online",
        "account_name": adapter.get_account_name(),
        "account_id": ctx.account_id  # 계좌 중심: 프론트엔드에서 사용
    }

@router.get("/system/version")
async def get_system_version():
    return {"version": settings.PROJECT_VERSION}

import time

# Simple In-Memory Cache
PRICE_CACHE = {} # { symbol: { 'data': ..., 'ts': ... } }
BALANCE_CACHE = {} # { user_id: { 'data': ..., 'ts': ... } }

@router.get("/price/{symbol}")
async def get_price(symbol: str, adapter: ExchangeInterface = Depends(get_exchange_adapter)):
    # Returns { "symbol": "...", "price": 100, "name": "Samsung" }
    current_time = time.time()
    
    # 1. Check Cache (TTL 1.0s)
    if symbol in PRICE_CACHE:
        entry = PRICE_CACHE[symbol]
        if current_time - entry['ts'] < 1.0:
            return entry['data']

    # 2. Fetch Real
    data = await adapter.get_current_price(symbol)
    
    # 3. Update Cache
    PRICE_CACHE[symbol] = {
        'data': data,
        'ts': current_time
    }
    
    return data

@router.get("/balance")
async def get_balance(ctx: UserAccountContext = Depends(get_user_context)):
    current_time = time.time()
    user_id = ctx.user_id

    # 1. Check User-specific Cache (TTL 2.0s)
    if user_id in BALANCE_CACHE:
        cache_entry = BALANCE_CACHE[user_id]
        if cache_entry['data'] and (current_time - cache_entry['ts'] < 2.0):
            return cache_entry['data']

    # 2. Get user-specific adapter and fetch balance
    adapter = ctx.get_exchange_adapter()
    data = await adapter.get_balance()

    # 3. Update User-specific Cache
    BALANCE_CACHE[user_id] = {'data': data, 'ts': current_time}

    return data

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
    db: Session = Depends(get_db),
    ctx: UserAccountContext = Depends(get_user_context)
):
    adapter = ctx.get_exchange_adapter()
    account_id = ctx.account_id

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
    
    # 1. Calculate Quantity using OrderService
    from ..services.order_service import OrderService
    
    # Check if balance info is needed
    balance_info = None
    if order.mode in ["percent_cash", "percent_holding"]:
         balance_info = await adapter.get_balance()

    try:
        quantity = OrderService.calculate_quantity(
            mode=order.mode,
            current_price=current_price,
            balance_info=balance_info,
            order_price=order.price,
            price_type=order.price_type,
            quantity=order.quantity,
            amount=order.amount,
            percent=order.percent,
            order_type=order.order_type,
            symbol=order.symbol
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if quantity <= 0:
        raise HTTPException(status_code=400, detail="Calculated quantity is 0 or invalid")

    # 2. Execute Order using OrderExecutionService
    from ..services.order_execution_service import OrderExecutionService, OrderExecutionError

    service = OrderExecutionService(adapter)
    try:
        result = await service.execute_order(
            symbol=order.symbol,
            side=order.order_type.lower(),
            quantity=quantity,
            price=calculated_price
        )
    except OrderExecutionError as e:
        raise HTTPException(status_code=400, detail=e.message)

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
                            account_id=account_id,
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
                            account_id=account_id,
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
    db: Session = Depends(get_db),
    ctx: UserAccountContext = Depends(get_user_context)
):
    # Validation
    if order.trigger_price <= 0:
        raise HTTPException(status_code=400, detail="Trigger price must be > 0")

    # Require active account
    active_account = ctx.require_account()
    adapter = ctx.get_exchange_adapter()

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
            account_id=active_account.id,  # 계좌별 분리
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
            highest_price=order.trigger_price if order.condition_type == "TRAILING_STOP" else None, # Initialize High Water Mark
            mode="REAL"
        )
        db.add(cond_order)
        db.commit()
        db.refresh(cond_order)

        return {
            "status": "success",
            "message": f"Watch Order Registered: {order.order_type.upper()} {order.condition_type}",
            "id": cond_order.id
        }

    except HTTPException:
        raise
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

@router.get("/orders/conditions/active")
async def get_active_conditions(
    db: Session = Depends(get_db),
    ctx: UserAccountContext = Depends(get_user_context)
):
    from ..models.condition import ConditionalOrder, ConditionStatus
    try:
        if not ctx.has_active_account:
            return []

        # Filter by Status AND account_id
        conditions = db.query(ConditionalOrder).filter(
            ConditionalOrder.status == ConditionStatus.PENDING,
            ConditionalOrder.account_id == ctx.account_id
        ).order_by(ConditionalOrder.created_at.desc()).all()
        return conditions
    except Exception as e:
         raise HTTPException(status_code=500, detail=str(e))

@router.delete("/orders/conditions/{condition_id}")
async def cancel_condition(
    condition_id: int,
    db: Session = Depends(get_db),
    ctx: UserAccountContext = Depends(get_user_context)
):
    from ..models.condition import ConditionalOrder, ConditionStatus
    try:
        # Find condition that belongs to user's account
        condition = db.query(ConditionalOrder).filter(
            ConditionalOrder.id == condition_id,
            ConditionalOrder.account_id == ctx.account_id
        ).first()

        if not condition:
            raise HTTPException(status_code=404, detail="Condition not found or access denied")

        condition.status = ConditionStatus.CANCELLED
        db.commit()
        return {"status": "success", "message": f"Condition {condition_id} cancelled"}
    except HTTPException:
        raise
    except Exception as e:
         raise HTTPException(status_code=500, detail=str(e))

@router.get("/ohlcv/{symbol}")
async def get_ohlcv(
    symbol: str, 
    interval: str = "1m", 
    days: int = 365, 
    limit: int = 100000,
    date: str = None # Optional: YYYYMMDD
):
    """
    Get OHLCV Data.
    If 'date' is provided (YYYYMMDD), fetches data for that specific day.
    Otherwise fetches last 'days' history.
    """
    from ..services.market_data import MarketDataService
    service = MarketDataService()
    
    if date:
        # Fetch specific date (Intraday History)
        data = await service.get_candles_by_date(symbol, interval, date)
    else:
        # Default fetch
        data = await service.get_candles(symbol, interval, days, limit)
        
    return data

@router.get("/trade/history")
async def get_trade_history_integrated(
    limit: int = 1000,
    db: Session = Depends(get_db),
    ctx: UserAccountContext = Depends(get_user_context)
):
    """
    Fetch executed trades AND composite market data for Visual Analysis.
    Returns composite object: { trades: [], multi_ohlcv_data: { sym: [] }, strategies_config: [] }
    """
    from ..models.live_trading import LiveTradeExecution, LiveBotSession
    from ..models.strategy_config import StrategyConfig
    from ..services.market_data import MarketDataService
    from sqlalchemy.orm import joinedload

    account_id = ctx.account_id

    # 1. Get Active Strategies Config (Source of Truth for "Screen Context")
    # We query active configurations for the user's account
    strategies_config = []

    # Fetch all active configs sorted by rank for the user's account
    db_configs = db.query(StrategyConfig).filter(
        StrategyConfig.account_id == account_id,
        StrategyConfig.is_active == True
    ).order_by(StrategyConfig.rank).all()
    
    involved_symbols = set()
    
    for c in db_configs:
        cfg = c.config_json
        if cfg and isinstance(cfg, dict):
            # Ensure symbol exists
            if 'symbol' in cfg:
                strategies_config.append(cfg)
                involved_symbols.add(cfg['symbol'])
                
    # If no active configs found, try fallback to latest session for user's account
    if not strategies_config and account_id:
        last_session = db.query(LiveBotSession).filter(
            LiveBotSession.account_id == account_id
        ).order_by(LiveBotSession.started_at.desc()).first()
        if last_session and last_session.strategy_config:
            strategies_config = last_session.strategy_config
            # Collect symbols
            if isinstance(strategies_config, list):
                for cfg in strategies_config:
                    if isinstance(cfg, dict) and 'symbol' in cfg:
                        involved_symbols.add(cfg['symbol'])

    # 2. Fetch Market Data (OHLCV) - Replicating BacktestEngine Logic
    # We fetch data for ALL involved symbols to provide the "Background Chart"
    md_service = MarketDataService()
    multi_ohlcv_data = {}
    
    # Check "from_date" in Rank 1 config to determine range, or default to 1-2 year?
    # Backtest engine usually fetches based on config['from_date'] or duration.
    # We'll fetch a reasonable default info (e.g., 365 days) or parse from config.
    fetch_days = 365
    from_date = None
    
    if strategies_config and len(strategies_config) > 0:
        # Try to find 'from_date' in Rank 1
        rank1 = strategies_config[0]
        if 'from_date' in rank1:
            from_date = rank1['from_date']
        # Also check interval
        interval = rank1.get('interval', '30m')
    else:
        interval = '30m'

    # Fetch Logic
    for sym in involved_symbols:
        # We fetch enough data. Backtest usually fetches 1-2 years if needed.
        # Let's fetch 400 days to be safe.
        candles = await md_service.get_candles(sym, interval=interval, days=400)
        if candles:
            # Filter if from_date exists
            if from_date:
                candles = [c for c in candles if c['timestamp'] >= from_date]
            multi_ohlcv_data[sym] = candles
            
    # 3. Fetch Real Trades (Exclude Paper Trading) - filter by user's account
    trades_query = db.query(LiveTradeExecution).join(LiveBotSession).filter(
        LiveBotSession.is_paper == False,
        LiveBotSession.account_id == account_id
    ).order_by(LiveTradeExecution.signal_timestamp.desc()).limit(limit).all()
    
    trades_data = []
    
    for t in trades_query:
        # Dynamic Rank Calculation based on Current Config
        rank = 0
        symbol = t.symbol
        
        # Match symbol to current config to assign rank
        # This aligns historical trades to CURRENT view lanes.
        # (User might want to see how past trades fit onto current strategy lanes)
        found_rank = False
        for i, cfg in enumerate(strategies_config):
            if cfg.get('symbol') == symbol:
                rank = i + 1
                found_rank = True
                break
        
        # If not found in current config, maybe use the session's recorded config?
        # But for Visual Context, we often want to see "Where does this trade fall in my current lanes?"
        # If the symbol is not in current lanes, it will have Rank 0 or show up as "Other".
        # Let's fallback to original rank if available or 0.
        if not found_rank and t.session and t.session.strategy_config:
             # Try to find rank in the SESSION'S config
             try:
                for idx, scfg in enumerate(t.session.strategy_config):
                    if scfg.get('symbol') == symbol:
                        rank = idx + 1
                        break
             except: pass

        trades_data.append({
            "time": t.signal_timestamp.isoformat(),
            "price": float(t.executed_price) if t.executed_price is not None else 0.0,
            "symbol": t.symbol,
            "quantity": float(t.filled_quantity) if t.filled_quantity is not None else 0.0,
            "type": t.signal_type, # 'BUY' or 'SELL'
            "pnl": float(t.realized_pnl) if t.realized_pnl is not None else 0.0,
            "strategy_rank": rank 
        })
        
        # User Rule: Everything from Kiwoom is 1m. We fetch 1m from DB and let frontend/backend handle sampling.
        # FIX: Force '1m' fetch.
        candles = await service.get_candles(sym, interval="1m", days=365, limit=50000)
        
        if not candles:
             # FIX: Fail Loudly if data is missing.
             raise HTTPException(
                 status_code=404, 
                 detail=f"No 1m Market Data found for symbol {sym}. Please ensure data is collected."
             )
             
        multi_ohlcv[sym] = candles

    # 4. Get Rank 1 Start Date for Timeline Anchoring
    rank1_start_date = None
    try:
        if strategies_config:
            rank1_symbol = None
            if isinstance(strategies_config, list) and len(strategies_config) > 0:
                rank1_symbol = strategies_config[0].get('symbol')
            elif isinstance(strategies_config, dict):
                # Check if it's a single strategy config (has 'symbol' key directly)
                if 'symbol' in strategies_config:
                    rank1_symbol = strategies_config.get('symbol')
                else:
                    # Fallback if config is dict of ranks
                    first_val = next(iter(strategies_config.values()))
                    if isinstance(first_val, dict):
                        rank1_symbol = first_val.get('symbol')

            if rank1_symbol and rank1_symbol in multi_ohlcv:
                candles = multi_ohlcv[rank1_symbol]
                # candles should be list of dicts
                if isinstance(candles, list) and len(candles) > 0:
                    rank1_start_date = candles[0].get('timestamp')
                elif isinstance(candles, dict):
                    # Should not happens if resample returns list, but just in case
                    pass
    except Exception as e:
        print(f"Error extracting Rank 1 Start Date: {e}")
        pass

    return {
        "trades": trades_data,
        "multi_ohlcv_data": multi_ohlcv,
        "strategies_config": strategies_config,
        "strategy_id": "live_integrated_view",
        "total_trades": len(trades_data),
        "rank1_start_date": rank1_start_date # Used by IntegratedAnalysis to anchor Start Time
    }

# --- Data Models for Context Request ---
class IntegratedConfigItem(BaseModel):
    id: str
    rank: int
    config: Dict[str, Any]
    strategy_id: str
    symbol: str

class TradeHistoryContextRequest(BaseModel):
    configs: List[IntegratedConfigItem]
    symbol: str
    interval: str = "30m"
    days: int = 365
    from_date: Optional[str] = None
    limit: int = 1000
    is_paper: Optional[bool] = None  # None=all, True=paper only, False=real only

@router.post("/trade/history-context")
async def get_trade_history_context(
    request: TradeHistoryContextRequest,
    db: Session = Depends(get_db),
    ctx: UserAccountContext = Depends(get_user_context)
):
    """
    Fetch executed trades matching the provided Frontend Configuration.
    Uses 'fetch_visualization_feeds' to generate identical background charts to Integrated Tab.
    """
    from ..models.live_trading import LiveTradeExecution, LiveBotSession
    from sqlalchemy.orm import joinedload

    account_id = ctx.account_id

    # 1. Extract Configs (Source of Truth is Frontend)
    strategies_config = [c.config for c in request.configs]

    # Ensure symbols are set fallback
    for i, cfg in enumerate(strategies_config):
        if 'symbol' not in cfg:
            cfg['symbol'] = request.configs[i].symbol or request.symbol

    # 2. Fetch Market Data (Identical Logic to Integrated Tab)
    multi_ohlcv_data = await fetch_visualization_feeds(
        strategies_config=strategies_config,
        global_symbol=request.symbol,
        interval=request.interval,
        duration_days=request.days,
        from_date=request.from_date,
        preloaded_feeds=None # Live mode has no preloaded simulation data
    )

    # 3. Fetch Trades (filtered by paper/real mode and user's account)
    trades_q = db.query(LiveTradeExecution).join(LiveBotSession).filter(
        LiveBotSession.account_id == account_id
    )
    if request.is_paper is not None:
        trades_q = trades_q.filter(LiveBotSession.is_paper == request.is_paper)
    trades_query = trades_q.order_by(LiveTradeExecution.signal_timestamp.desc()).limit(request.limit).all()
    
    trades_data = []
    
    for t in trades_query:
        # Dynamic Rank Calculation based on Request Config
        rank = 0
        symbol = t.symbol
        
        # Match symbol to current config to assign rank
        found_rank = False
        for i, cfg in enumerate(strategies_config):
            if cfg.get('symbol') == symbol:
                rank = i + 1
                found_rank = True
                break
        
        # Fallback to Session Config if not found in Request Config? 
        # User wants to see how trades fit CURRENT View. So if not found, it's Rank 0 (Other).
        # We can optionally check session config, but adhering to "Visual Context" implies strict matching.
        # Let's keep strict matching to Request Config for clarity.
        
        trades_data.append({
            "time": t.signal_timestamp.isoformat(),
            "price": float(t.executed_price) if t.executed_price is not None else 0.0,
            "symbol": t.symbol,
            "quantity": float(t.filled_quantity) if t.filled_quantity is not None else 0.0,
            "type": t.signal_type, 
            "pnl": float(t.realized_pnl) if t.realized_pnl is not None else 0.0,
            "strategy_rank": rank 
        })
        
    # 4. Get Rank 1 Start Date
    rank1_start_date = None
    if strategies_config and len(strategies_config) > 0:
        r1_sym = strategies_config[0].get('symbol')
        if r1_sym and r1_sym in multi_ohlcv_data:
            candles = multi_ohlcv_data[r1_sym]
            if candles:
                 rank1_start_date = candles[0].get('timestamp')

    return {
        "trades": trades_data,
        "multi_ohlcv_data": multi_ohlcv_data,
        "strategies_config": strategies_config,
        "strategy_id": "live_integrated_view",
        "total_trades": len(trades_data),
        "rank1_start_date": rank1_start_date
    }


# --- Lightweight Trade List Endpoint (Step 1 of 2-step architecture) ---
class TradeListRequest(BaseModel):
    is_paper: Optional[bool] = None  # None=all, True=paper, False=real
    limit: int = 500

@router.post("/trade/history-list")
async def get_trade_history_list(
    request: TradeListRequest,
    db: Session = Depends(get_db),
    ctx: UserAccountContext = Depends(get_user_context)
):
    """
    Lightweight endpoint: returns only trade executions grouped into cycles.
    No OHLCV data fetched. Fast DB query only.
    """
    from ..models.live_trading import LiveTradeExecution, LiveBotSession
    from sqlalchemy import asc

    account_id = ctx.account_id

    # Filter by user's account
    trades_q = db.query(LiveTradeExecution).join(LiveBotSession).filter(
        LiveBotSession.account_id == account_id
    )
    if request.is_paper is not None:
        trades_q = trades_q.filter(LiveBotSession.is_paper == request.is_paper)

    trades = trades_q.order_by(asc(LiveTradeExecution.signal_timestamp)).limit(request.limit).all()

    # Group trades into cycles (BUY → SELL pairs)
    # A cycle starts with a BUY and ends with a SELL for the same symbol+session
    cycles = []
    open_positions = {}  # key: (session_id, symbol) -> list of buys

    for t in trades:
        key = (t.session_id, t.symbol)
        trade_dict = {
            "id": t.id,
            "session_id": t.session_id,
            "symbol": t.symbol,
            "signal_type": t.signal_type,
            "signal_timestamp": t.signal_timestamp.isoformat() if t.signal_timestamp else None,
            "theoretical_price": float(t.theoretical_price) if t.theoretical_price else 0,
            "executed_price": float(t.executed_price) if t.executed_price else 0,
            "filled_quantity": float(t.filled_quantity) if t.filled_quantity else 0,
            "realized_pnl": float(t.realized_pnl) if t.realized_pnl else 0,
            "fees": float(t.fees) if t.fees else 0,
            "is_paper": t.is_paper,
            "status": t.status,
            "trade_metadata": t.trade_metadata,
            "config_snapshot": t.config_snapshot,
            "strategy_name": t.session.strategy_name if t.session else None,
        }

        if t.signal_type == "BUY":
            if key not in open_positions:
                open_positions[key] = []
            open_positions[key].append(trade_dict)
        elif t.signal_type == "SELL":
            buys = open_positions.get(key, [])
            # Get strategy_name and config_snapshot from first BUY or SELL
            first_config = buys[0]["config_snapshot"] if buys and buys[0].get("config_snapshot") else trade_dict.get("config_snapshot")
            strategy_name = buys[0]["strategy_name"] if buys and buys[0].get("strategy_name") else trade_dict.get("strategy_name")
            cycle = {
                "symbol": t.symbol,
                "session_id": t.session_id,
                "is_paper": t.is_paper,
                "strategy_name": strategy_name,
                "config_snapshot": first_config,
                "buys": list(buys),
                "sell": trade_dict,
                "entry_time": buys[0]["signal_timestamp"] if buys else trade_dict["signal_timestamp"],
                "exit_time": trade_dict["signal_timestamp"],
                "total_buy_qty": sum(b["filled_quantity"] for b in buys),
                "total_buy_cost": sum(b["executed_price"] * b["filled_quantity"] for b in buys),
                "sell_price": trade_dict["executed_price"],
                "sell_qty": trade_dict["filled_quantity"],
                "fees": sum(b["fees"] for b in buys) + trade_dict["fees"],
                "num_entries": len(buys),
            }
            # Calculate avg entry price
            if cycle["total_buy_qty"] > 0:
                cycle["avg_entry_price"] = cycle["total_buy_cost"] / cycle["total_buy_qty"]
            else:
                cycle["avg_entry_price"] = 0
            # Calculate return %
            if cycle["avg_entry_price"] > 0:
                cycle["return_pct"] = ((cycle["sell_price"] - cycle["avg_entry_price"]) / cycle["avg_entry_price"]) * 100
            else:
                cycle["return_pct"] = 0
            # Calculate realized_pnl: use DB value if set, otherwise compute from prices
            db_pnl = trade_dict["realized_pnl"]
            if db_pnl and db_pnl != 0:
                cycle["realized_pnl"] = db_pnl
            else:
                # Fallback: compute from avg entry price and sell price
                sell_qty = cycle["sell_qty"] or cycle["total_buy_qty"]
                cycle["realized_pnl"] = round((cycle["sell_price"] - cycle["avg_entry_price"]) * sell_qty, 2) if cycle["avg_entry_price"] > 0 else 0

            cycles.append(cycle)
            open_positions[key] = []  # Reset for next cycle

    # Any remaining open positions (no SELL yet)
    open_cycles = []
    for key, buys in open_positions.items():
        if buys:
            open_cycles.append({
                "symbol": key[1],
                "session_id": key[0],
                "is_paper": buys[0]["is_paper"],
                "strategy_name": buys[0].get("strategy_name"),
                "config_snapshot": buys[0].get("config_snapshot"),
                "buys": buys,
                "sell": None,
                "entry_time": buys[0]["signal_timestamp"],
                "exit_time": None,
                "total_buy_qty": sum(b["filled_quantity"] for b in buys),
                "total_buy_cost": sum(b["executed_price"] * b["filled_quantity"] for b in buys),
                "sell_price": None,
                "sell_qty": 0,
                "realized_pnl": 0,
                "fees": sum(b["fees"] for b in buys),
                "num_entries": len(buys),
                "avg_entry_price": sum(b["executed_price"] * b["filled_quantity"] for b in buys) / sum(b["filled_quantity"] for b in buys) if sum(b["filled_quantity"] for b in buys) > 0 else 0,
                "return_pct": 0,
                "status": "OPEN",
            })

    return {
        "cycles": sorted(cycles, key=lambda c: c["exit_time"] or "", reverse=True),
        "open_cycles": open_cycles,
        "total_cycles": len(cycles),
        "total_open": len(open_cycles),
        "total_trades": len(trades),
    }
