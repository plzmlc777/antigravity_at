import asyncio
import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.services.market_data import MarketDataService
from app.db.session import SessionLocal

async def test_fetch():
    print("Testing MarketDataService for 085310 (Daily)...")
    service = MarketDataService()
    
    # 1. Clear existing data to force fetch (Optional, but good for robust test)
    # print("Clearing existing data...")
    # db = SessionLocal()
    # service.delete_ohlcv_by_symbol(db, "085310")
    # db.close()

    # 2. Fetch
    try:
        # Request 1 year of Daily data
        candles = await service.get_candles("085310", "1d", days=365)
        
        print(f"Result Count: {len(candles)}")
        if candles:
            print("First Candle:", candles[0])
            print("Last Candle:", candles[-1])
        else:
            print("FAILED: No candles returned.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_fetch())
