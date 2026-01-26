from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Dict, Any
from ..db.session import get_db
from ..services.market_data import MarketDataService
from ..models.ohlcv import OHLCV
from .auth import get_current_active_admin
from datetime import datetime, timedelta
from sqlalchemy import func
from pydantic import BaseModel
from ..adapters.kiwoom_real import KiwoomRealAdapter
from typing import List, Optional

router = APIRouter()

@router.get("/status/{symbol}")
def get_data_status(symbol: str, interval: str = "1m", db: Session = Depends(get_db)):
    """
    Check if we have fresh data for the symbol (within last 24 hours).
    Returns: { "symbol": str, "last_updated": str, "is_fresh": bool, "count": int }
    """
    # Find the latest timestamp for this symbol
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
    Uses KiwoomRealAdapter.
    """
    try:
        adapter = KiwoomRealAdapter()
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
    days: int = 365  # Max 1 year (API limit)
    backfill: bool = False  # If True, fetch ALL data up to 'days' even if some exists

@router.post("/fetch/{symbol}")
async def fetch_market_data(symbol: str, req: FetchRequest):
    """
    Trigger fetching data for the symbol.
    Req body: { "interval": "1m", "days": 365, "backfill": false } (optional)

    backfill=True: Fetch full history regardless of existing data (slower, use for initial setup)
    backfill=False: Incremental update, stop when hitting existing data (default, faster)
    """
    service = MarketDataService()

    # Run fetch with backfill option
    # backfill=True: Fetch full history even if some data exists (slower, for filling gaps)
    # backfill=False: Stop when hitting existing data (incremental, faster)
    added_count = await service.fetch_history(symbol, req.interval, req.days, backfill=req.backfill)

    return {
        "status": "success",
        "message": f"Fetched {req.interval} data for {symbol}" + (" (backfill)" if req.backfill else ""),
        "added": added_count
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
        service = MarketDataService()
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
