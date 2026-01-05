import sys
import os
import asyncio
from datetime import datetime

sys.path.append(os.getcwd())
from backend.app.services.market_data import MarketDataService

async def inspect():
    service = MarketDataService()
    symbol = "233740" # From logs
    target_date = "2025-01-14"
    
    print(f"--- Inspecting {symbol} on {target_date} ---")
    
    # 1. Check 1m Data (Source)
    # We need to manually query or fetch "1m" specifically for that day.
    # get_candles might trigger fetch if missing, but we want to see what's in DB.
    # We'll use get_candles("1m") and filter.
    
    print("\n[checking 1m data...]")
    digits_1m = await service.get_candles(symbol, "1m", days=400) # Ensure coverage
    day_1m = [c for c in digits_1m if c['timestamp'].startswith(target_date)]
    day_1m.sort(key=lambda x: x['timestamp'])
    
    if not day_1m:
        print("NO 1m Data found for this date.")
    else:
        print(f"Found {len(day_1m)} 1m candles.")
        print(f"First 1m: {day_1m[0]['timestamp']}")
        print(f"First 5 1m: {[c['timestamp'].split(' ')[1] for c in day_1m[:5]]}")
        
        # Check specifically for 09:00 - 09:05
        early_morning = [c for c in day_1m if "09:00" <= c['timestamp'].split(' ')[1] <= "09:10"]
        if early_morning:
            print(f"Early Morning 1m Data Exists: {[c['timestamp'].split(' ')[1] for c in early_morning]}")
        else:
            print("CRITICAL: No 1m data between 09:00 and 09:10")

    # 2. Check 15m Data (Aggregated)
    print("\n[checking 15m data...]")
    digits_15m = await service.get_candles(symbol, "15m", days=400)
    day_15m = [c for c in digits_15m if c['timestamp'].startswith(target_date)]
    day_15m.sort(key=lambda x: x['timestamp'])
    
    if not day_15m:
        print("NO 15m Data found.")
    else:
        print(f"Found {len(day_15m)} 15m candles.")
        print(f"First 15m: {day_15m[0]['timestamp']}")
        print(f"First 5 15m: {[c['timestamp'].split(' ')[1] for c in day_15m[:5]]}")

if __name__ == "__main__":
    asyncio.run(inspect())
