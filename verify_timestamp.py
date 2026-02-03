import sys
import os
import asyncio
from datetime import datetime

sys.path.append(os.getcwd())
from backend.app.services.market_data import MarketDataService

async def verify():
    service = MarketDataService()
    # Fetch data
    print("Fetching data...")
    raw_data = await service.get_candles("005930", "15m", days=5)
    
    # Simulate BacktestEngine Filtering
    from_date = "2026-01-05"
    print(f"Applying Filter: timestamp >= '{from_date}'")
    
    filtered_feed = [c for c in raw_data if c['timestamp'] >= from_date]
    
    if not filtered_feed:
        print("Filtered Feed is EMPTY.")
        return

    first_candle = filtered_feed[0]
    print(f"First Candle Timestamp: {first_candle['timestamp']}")
    
    if "09:00:00" in first_candle['timestamp']:
        print("SUCCESS: 09:00:00 is present.")
    else:
        print(f"FAILURE: Starts at {first_candle['timestamp']}. 09:00 is missing!")
        
        # Check previous candles to see why 09:00 was dropped or if it wasn't there
        print("Checking raw data around boundary...")
        for c in raw_data:
            if "2026-01-05" in c['timestamp']:
                print(f"Raw: {c['timestamp']}")
                if "09:30" in c['timestamp']: break

if __name__ == "__main__":
    asyncio.run(verify())
