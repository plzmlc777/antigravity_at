import requests
import json
import sys

# Script to verify if the Backtest API returns 09:00 candles
# Usage: python3 verify_api_0900.py

BASE_URL = "http://localhost:8000/api/v1"

def verify_backtest_api():
    # 1. Get a Strategy ID (We might need to list strategies or assume one exists)
    # StrategyView usually loads a strategy. We can use a mock ID or fetch one.
    # For simplicity, we'll try to create a dummy payload for a known strategy if needed,
    # or just assume specific endpoint.
    # Actually, the backtest endpoint is /strategies/{id}/backtest/integrated or similar?
    # No, usually /strategies/{id}/backtest.
    # Let's list strategies first to get an ID.
    
    try:
        # We need a strategy ID. Let's create a temporary default one or list existing.
        # GET /strategies/
        resp = requests.get(f"{BASE_URL}/strategies/")
        if resp.status_code != 200:
            print(f"Failed to list strategies: {resp.status_code}")
            return
            
        strategies = resp.json()
        if not strategies:
            print("No strategies found. Creating a dummy strategy...")
            # Create dummy
            create_payload = {
                "name": "Test Strategy",
                "symbol": "005930", # Samsung Electronics
                "interval": "15m",
                "strategy_type": "DUMMY" 
            }
            # POST not fully defined here, skipping.
            print("Cannot proceed without strategy.")
            return

        strategy_id = strategies[0]['id']
        print(f"Using Strategy ID: {strategy_id} ({strategies[0]['name']})")
        
        # 2. Run Backtest with 15m interval
        payload = {
            "initial_capital": 10000000,
            "period": 5, # days
            "interval": "15m", # Explicitly request 15m
            "strategy_config": {
                "interval": "15m",
                "symbol": "005930"
            }
        }
        
        print(f"Requesting Backtest for 15m...")
        # Note: The endpoint might be /strategies/{id}/backtest
        # Or /strategies/backtest (if stateless).
        # Based on file `backend/app/api/mock_strategies.py`, it's likely:
        # router.post("/{strategy_id}/backtest", ...)
        
        url = f"{BASE_URL}/strategies/{strategy_id}/backtest"
        resp = requests.post(url, json=payload)
        
        if resp.status_code != 200:
            print(f"Backtest Failed: {resp.status_code} {resp.text}")
            return
            
        result = resp.json()
        ohlcv = result.get("ohlcv_data", [])
        print(f"Received {len(ohlcv)} candles.")
        
        if not ohlcv:
            print("No OHLCV data in response.")
            return

        # 3. Check for 09:00
        found_0900 = False
        print("\nChecking for 09:00 timestamps...")
        for item in ohlcv:
            ts = item.get('time') # Likely string or timestamp
            # API usually returns UNIX int OR String?
            # MarketDataService returns String "%Y-%m-%d %H:%M:%S"
            # BacktestEngine passes it through.
            
            str_ts = str(ts)
            if "09:00:00" in str_ts:
                print(f"FOUND API 09:00: {ts}")
                found_0900 = True
            elif "09:15:00" in str_ts:
                print(f"FOUND API 09:15: {ts}")
                
        if not found_0900:
            print("CRITICAL: 09:00 MISSING in API Response!")
            
        print("\nFirst 5 API Candles:")
        for item in ohlcv[:5]:
            print(item.get('time'))

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    verify_backtest_api()
