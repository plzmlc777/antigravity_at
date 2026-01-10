
import sys
import os
import asyncio
from datetime import datetime

# Adjust path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.core.waterfall_engine import BacktestContext

def test_price_cache():
    print("--- Testing Price Cache Fix ---")
    
    # 1. Setup Feeds
    # Symbol TEST: Stops at 10:00.
    feed_test = [
        {"timestamp": "2024-01-01T09:00:00", "close": 1000},
        {"timestamp": "2024-01-01T10:00:00", "close": 1100} 
    ]
    # Symbol BTC: Goes to 12:00 (Driving the clock)
    feed_btc = [
        {"timestamp": "2024-01-01T09:00:00", "close": 50000},
        {"timestamp": "2024-01-01T10:00:00", "close": 51000},
        {"timestamp": "2024-01-01T11:00:00", "close": 52000}, # TEST missing here
        {"timestamp": "2024-01-01T12:00:00", "close": 53000}  # TEST missing here
    ]
    
    feeds = {"TEST": feed_test, "BTC": feed_btc}
    
    # 2. Setup Context
    context = BacktestContext(feeds, initial_capital=10000, primary_symbol="BTC")
    
    # Simulate Buy of TEST at 09:00
    context.current_timestamp = "2024-01-01T09:00:00"
    cols_price = context.get_current_price("TEST") 
    print(f"09:00 TEST Price: {cols_price} (Expected 1000)")
    context.buy("TEST", 1, price=1000)
    context.update_equity()
    
    # 10:00 Update
    context.current_timestamp = "2024-01-01T10:00:00"
    cols_price = context.get_current_price("TEST")
    print(f"10:00 TEST Price: {cols_price} (Expected 1100)")
    context.update_equity()
    
    # 11:00 Update (Data Missing for TEST in feeds)
    # The Fix should return cached 1100.
    context.current_timestamp = "2024-01-01T11:00:00"
    cols_price = context.get_current_price("TEST")
    print(f"11:00 TEST Price: {cols_price} (Expected 1100 CACHED)")
    context.update_equity()
    
    # Verify Equity
    # At 11:00, Equity = Cash (9000) + Holdings (1 * 1100) = 10100.
    # If Fix failed, Price=0 -> Value=0 -> Equity=9000.
    
    last_equity = context.equity_curve[-1]['equity']
    print(f"Final Equity at 11:00: {last_equity}")
    
    if last_equity == 10100:
        print("SUCCESS: Price Caching Works. Equity held value.")
    else:
        print(f"FAILURE: Equity crashed. Expected 10100, Got {last_equity}")
        sys.exit(1)

if __name__ == "__main__":
    test_price_cache()
