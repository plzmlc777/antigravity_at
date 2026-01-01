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
    days: int = 365

@router.post("/fetch/{symbol}")
async def fetch_market_data(symbol: str, req: FetchRequest):
    """
    Trigger fetching data for the symbol.
    Req body: { "interval": "1m", "days": 365 } (optional)
    """
    service = MarketDataService()
    
    # Run synchronously to return count
    added_count = await service.fetch_history(symbol, req.interval, req.days)
    
    return {
        "status": "success", 
        "message": f"Fetched {req.interval} data for {symbol}",
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
