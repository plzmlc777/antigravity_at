
import requests
import sys

BASE_URL = "http://localhost:8001/api/v1/market-data"

def check_reset(symbol="KRW-BTC"):
    # 1. Check Status (Get Count)
    try:
        r = requests.get(f"{BASE_URL}/status/{symbol}")
        if r.status_code != 200:
            print(f"Status check failed: {r.status_code}")
            return
        
        initial_count = r.json().get("count", 0)
        print(f"Initial Count for {symbol}: {initial_count}")
        
    except Exception as e:
        print(f"Error checking status: {e}")
        return

    # 2. Reset Data
    try:
        print(f"Resetting data for {symbol}...")
        r = requests.delete(f"{BASE_URL}/reset/{symbol}")
        if r.status_code == 200:
            print("Reset API succeeded.")
            print(r.json())
        else:
            print(f"Reset API failed: {r.status_code}, {r.text}")
            return
            
    except Exception as e:
        print(f"Error calling reset API: {e}")
        return

    # 3. Verify Count is 0
    try:
        r = requests.get(f"{BASE_URL}/status/{symbol}")
        final_count = r.json().get("count", 0)
        print(f"Final Count for {symbol}: {final_count}")
        
        if final_count == 0:
            print("VERIFICATION SUCCESS: Data count is 0.")
        else:
            print("VERIFICATION FAILED: Data count is NOT 0.")
            
    except Exception as e:
        print(f"Error checking final status: {e}")

if __name__ == "__main__":
    check_reset()
