
import asyncio
import requests
import json
import sys

# Define base URL
BASE_URL = "http://localhost:8000/api/v1"

# Define Payload for Mock Backtest (Single Strategy)
payload = {
    "symbol": "BTC/KRW",
    "interval": "1m",
    "days": 60,
    "initial_capital": 10000000,
    "config": {
        "buy_delay": 2,
        "target_percent": 1.0,
        "loss_cut_percent": 3.0,
        "trailing_stop_percent": 5.0,
        "market_check": True
    }
}

def verify_migration():
    print("Running Backtest Endpoint (should use Integrated Engine)...")
    try:
        # We need to target the Mock Strategy endpoint
        # The URL is /api/v1/strategies/{strategy_id}/backtest
        url = f"{BASE_URL}/strategies/time_momentum/backtest"
        
        response = requests.post(url, json=payload)
        
        if response.status_code == 200:
            result = response.json()
            # print(json.dumps(result, indent=2))
            
            # Key verification: Check for Integrated specific fields or behavior
            # The migration added 'rank_stats_list' to the return dict.
            # If this key exists, it confirms WaterfallBacktestEngine was used.
            
            if 'rank_stats_list' in result:
                print("SUCCESS: 'rank_stats_list' found in response.")
                print(f"Total Return: {result.get('total_return')}")
                print(f"Stats List: {len(result['rank_stats_list'])} ranks")
            else:
                print("FAILURE: 'rank_stats_list' NOT found. Migration might not be active.")
                
            # Check MDD Sign match (should be negative)
            mdd = result.get('max_drawdown', '0%')
            print(f"Max Drawdown: {mdd}")
            
        else:
            print(f"Error {response.status_code}: {response.text}")

    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    verify_migration()
