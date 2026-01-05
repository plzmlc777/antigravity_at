import asyncio
from backend.app.services.market_data import MarketDataService
from backend.app.db.session import SessionLocal
from backend.app.models.ohlcv import OHLCV
from datetime import datetime
import sys

# Mock settings to avoid API calls if possible, or just test aggregation logic
async def test_aggregation():
    service = MarketDataService()
    # 0. Find Active Symbol
    db = SessionLocal()
    # Get a symbol with most 1m data
    from sqlalchemy import func
    symbol_record = db.query(OHLCV.symbol, func.count(OHLCV.id)).filter(OHLCV.time_frame == '1m').group_by(OHLCV.symbol).order_by(func.count(OHLCV.id).desc()).first()
    
    if not symbol_record:
        print("No 1m data found in DB.")
        return
        
    symbol = symbol_record[0]
    count_1m = symbol_record[1]
    print(f"Detected Active Symbol: {symbol} (Count: {count_1m})")
    
    # 1. Check 1m Count (Redundant but consistent)
    # db = SessionLocal() 
    # removed redundant open
    # count_1m = db.query(OHLCV).filter(OHLCV.symbol == symbol, OHLCV.time_frame == '1m').count()
    # print(f"1m Count for {symbol}: {count_1m}")
    # db.close()

    if count_1m < 100:
        print("Not enough 1m data to test.")
        return

    # 2. Run Aggregation Logic manually
    print("\n--- Testing Aggregation Logic (Internal) ---")
    # Simulate what fetch_history does
    days = 3650
    from datetime import timedelta
    cutoff_date = datetime.now() - timedelta(days=days + 1)
    
    db = SessionLocal()
    base_candles_db = db.query(OHLCV).filter(
        OHLCV.symbol == symbol, 
        OHLCV.time_frame == "1m",
        OHLCV.timestamp >= cutoff_date
    ).order_by(OHLCV.timestamp.asc()).all()
    
    base_candles = [
        {
            "timestamp": c.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume
        }
        for c in base_candles_db
    ]
    print(f"Loaded {len(base_candles)} 1m candles from DB.")
    
    # Aggregate to 30m
    agg_30m = service._aggregate_candles(base_candles, "30m")
    print(f"Aggregated to 30m: {len(agg_30m)} candles.")
    
    # Aggregate to 1h (60m)
    agg_60m = service._aggregate_candles(base_candles, "60m")
    print(f"Aggregated to 60m: {len(agg_60m)} candles.")
    
    db.close()

if __name__ == "__main__":
    import os
    sys.path.append(os.getcwd())
    asyncio.run(test_aggregation())
