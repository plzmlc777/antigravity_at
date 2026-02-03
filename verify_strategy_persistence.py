import requests
import json

BASE_URL = "http://localhost:8001/api/v1"

def verify_persistence():
    print("Verifying Strategy Persistence...")
    
    # 1. Create/Sync a config for a specific strategy
    strategy_id = "test_strategy_v1"
    configs = [
        {
            "tab_id": "tab-1-uuid",
            "strategy_id": strategy_id,
            "rank": 0,
            "is_active": True,
            "tab_name": "Rank 1",
            "config_json": {"symbol": "005930", "interval": "1m"}
        },
        {
            "tab_id": "tab-2-uuid",
            "strategy_id": strategy_id,
            "rank": 1,
            "is_active": True,
            "tab_name": "Rank 2",
            "config_json": {"symbol": "000660", "interval": "30m"}
        }
    ]
    
    print(f"Syncing configs for {strategy_id}...")
    try:
        res = requests.post(f"{BASE_URL}/strategy-configs/{strategy_id}/sync", json=configs)
        print(f"Sync Response: {res.status_code}")
        if res.status_code != 200:
            print(res.text)
            return
    except Exception as e:
        print(f"Sync Failed: {e}")
        return

    # 2. Retrieve configs for the same strategy
    print(f"Retrieving configs for {strategy_id}...")
    try:
        res = requests.get(f"{BASE_URL}/strategy-configs/{strategy_id}")
        data = res.json()
        print(f"Retrieve Response: {res.status_code}")
        print(f"Count: {len(data)}")
        
        found_symbols = [c['config_json']['symbol'] for c in data]
        print(f"Symbols found: {found_symbols}")
        
        if "005930" in found_symbols and "000660" in found_symbols:
            print("SUCCESS: Configs persisted and retrieved correctly.")
        else:
            print("FAILURE: Configs mismatch.")
            
    except Exception as e:
        print(f"Retrieve Failed: {e}")

    # 3. Retrieve for a DIFFERENT strategy (should be empty or different)
    other_strategy_id = "other_strategy"
    print(f"Retrieving configs for {other_strategy_id} (Should be empty)...")
    res = requests.get(f"{BASE_URL}/strategy-configs/{other_strategy_id}")
    data = res.json()
    print(f"Count: {len(data)}")
    if len(data) == 0:
         print("SUCCESS: Isolation verified.")
    else:
         print(f"FAILURE: Isolation failed, found {len(data)} items.")

if __name__ == "__main__":
    verify_persistence()
