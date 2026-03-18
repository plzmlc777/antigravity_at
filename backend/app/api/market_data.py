from ..core.config import DEFAULT_EXCHANGE, DEFAULT_DAYS
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Dict, Any
from ..db.session import get_db
from ..services.market_data_factory import get_market_data_service
from ..models.ohlcv import OHLCV
from .auth import get_current_active_admin
from datetime import datetime, timedelta
from sqlalchemy import func
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()

@router.get("/status/{symbol}")
def get_data_status(symbol: str, interval: str = "1m", db: Session = Depends(get_db)):
    """
    Check if we have fresh data for the symbol (within last 24 hours).
    Returns: { "symbol": str, "last_updated": str, "is_fresh": bool, "count": int }
    """
    # Normalize: try exact match first, then uppercase (Binance stores UPPER)
    last_record = db.query(OHLCV.timestamp).filter(
        OHLCV.symbol == symbol,
        OHLCV.time_frame == interval
    ).order_by(OHLCV.timestamp.desc()).first()

    if not last_record and symbol != symbol.upper():
        symbol = symbol.upper()
        last_record = db.query(OHLCV.timestamp).filter(
            OHLCV.symbol == symbol,
            OHLCV.time_frame == interval
        ).order_by(OHLCV.timestamp.desc()).first()

    count = db.query(func.count(OHLCV.id)).filter(
        OHLCV.symbol == symbol,
        OHLCV.time_frame == interval
    ).scalar()
    
    if not last_record:
        return {
            "symbol": symbol,
            "last_updated": None,
            "is_fresh": False,
            "count": 0
        }
    
    last_ts = last_record[0]
    
    # Define "fresh" as having data within the last 1 day (approximated for market days)
    now = datetime.now()
    # For daily candles, "fresh" might mean today's date if market closed, or yesterday.
    
    is_fresh = (now - last_ts) < timedelta(days=1)

    first_record = db.query(OHLCV.timestamp).filter(
        OHLCV.symbol == symbol,
        OHLCV.time_frame == interval
    ).order_by(OHLCV.timestamp.asc()).first()
    
    start_date = first_record[0].strftime("%y.%m.%d") if first_record else None

    return {
        "symbol": symbol,
        "last_updated": last_ts.strftime("%Y-%m-%d %H:%M:%S"),
        "start_date": start_date,
        "is_fresh": is_fresh,
        "count": count
    }

@router.get("/info/{symbol}")
async def get_symbol_info(symbol: str):
    """
    Get Real-time Symbol Info (Name, Price) to populate UI.
    Uses LiveManager's adapter which has active account credentials from DB.
    """
    try:
        from ..core.live_manager import LiveManager
        live_manager = LiveManager.get_instance()
        adapter = live_manager.adapter
        data = await adapter.get_current_price(symbol)
        return {
            "symbol": symbol,
            "name": data.get("name", ""),
            "price": data.get("price", 0)
        }
    except Exception as e:
        # Fallback if adapter fails (e.g. token issue)
        return {"symbol": symbol, "name": "", "error": str(e)}

class FetchRequest(BaseModel):
    interval: str = "1m"
    days: int = DEFAULT_DAYS
    backfill: bool = False
    exchange_name: str = DEFAULT_EXCHANGE

@router.post("/fetch/{symbol}")
async def fetch_market_data(symbol: str, req: FetchRequest, background_tasks: BackgroundTasks):
    """
    Trigger fetching data for the symbol (runs in background).
    Returns immediately; frontend polls /status/{symbol} for progress.

    Req body: { "interval": "1m", "days": 365, "backfill": false, "exchange_name": "Kiwoom" }
    exchange_name: Selects the correct data service (Kiwoom, Binance, BinanceFutures)
    """
    service = get_market_data_service(req.exchange_name)

    background_tasks.add_task(service.fetch_history, symbol, req.interval, req.days, backfill=req.backfill)

    return {
        "status": "started",
        "message": f"Fetching {req.interval} data for {symbol} in background",
        "added": -1
    }

@router.delete("/reset")
def reset_market_data(
    db: Session = Depends(get_db),
    admin_user=Depends(get_current_active_admin)
):
    """
    Delete ALL OHLCV data from the database.
    This creates a fresh start for charts.
    """
    try:
        # Delete all records
        num = db.query(OHLCV).delete()
        db.commit()
        return {"status": "success", "message": f"Successfully deleted {num} market data records."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
from .auth import get_current_user

@router.delete("/reset/{symbol}")
def reset_symbol_data(
    symbol: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Delete OHLCV data for a SPECIFIC symbol.
    """
    service = MarketDataService()
    try:
        num = service.delete_ohlcv_by_symbol(db, symbol)
        return {"status": "success", "message": f"Successfully deleted {num} records for {symbol}."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/candles/{symbol}")
async def get_candles(
    symbol: str, 
    interval: str = "1m", 
    date: Optional[str] = None, 
    limit: int = 1000,
    db: Session = Depends(get_db)
):
    """
    Fetch historical candles for a symbol.
    - If `date` (YYYY-MM-DD or YYYYMMDD) is provided, fetches candles for that specific day.
    - Otherwise, returns the most recent `limit` candles.
    """
    try:
        service = get_market_data_service()
        if date:
            # Normalized date string for service (YYYYMMDD)
            date_clean = date.replace("-", "").replace(".", "")
            return await service.get_candles_by_date(symbol, interval, date_clean)
        else:
            # Default fetch logic (recent limit) - reusing service if possible or keeping simplified query
            # For consistency, let's keep the simple query for limit-based fetch or implement get_candles_limit in service
            # To minimize risk, we keep existing limit logic but fix the date logic.
            
            # OR better: use service.get_candles if it supports limit logic well?
            # service.get_candles fetches LAST days.
            # Here we want LAST LIMIT candles.
            
            query = db.query(OHLCV).filter(
                OHLCV.symbol == symbol,
                OHLCV.time_frame == interval
            )
            candles = query.order_by(OHLCV.timestamp.asc()).limit(limit).all()
        
            return [
                {
                    "time": int(c.timestamp.timestamp()), # Unix Timestamp (Seconds) for Frontend
                    "open": float(c.open),
                    "high": float(c.high),
                    "low": float(c.low),
                    "close": float(c.close),
                    "volume": float(c.volume or 0) # Handle None safely
                }
                for c in candles
            ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Data Maintenance Endpoints ───────────────────────────────────────

@router.get("/maintenance/status")
async def get_maintenance_status():
    """Get data maintenance scheduler status."""
    from ..core.data_maintenance import data_maintenance_scheduler
    return data_maintenance_scheduler.get_status()


@router.post("/maintenance/run")
async def run_maintenance(background_tasks: BackgroundTasks):
    """
    Manually trigger data maintenance (gap detection + backfill).
    Runs in background and returns immediately.
    """
    from ..core.data_maintenance import data_maintenance_scheduler

    if data_maintenance_scheduler._is_executing:
        raise HTTPException(status_code=409, detail="Maintenance already in progress")

    background_tasks.add_task(data_maintenance_scheduler.run_maintenance)
    return {"status": "started", "message": "Data maintenance triggered in background"}
