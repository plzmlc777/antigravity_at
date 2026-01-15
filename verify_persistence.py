
import requests
import json

BASE_URL = "http://localhost:8001/api/v1"

def check_persistence():
    try:
        # Check Health (Root level)
        r = requests.get(f"http://localhost:8001/health")
        if r.status_code != 200:
            print(f"Health Check Failed: {r.status_code}")
            # Continue anyway to check persistence
        else:
             print("Health Check: OK")

        # Check Strategy Configs for default strategy 'time_momentum'
        strategy_id = "time_momentum"
        r = requests.get(f"{BASE_URL}/strategy-configs/{strategy_id}")
        
        if r.status_code == 200:
            data = r.json()
            print("Persistence Check: SUCCESS")
            print(f"Found {len(data)} configs for {strategy_id}")
            # print(json.dumps(data, indent=2))
        else:
            print(f"Persistence Check: FAILED (Status {r.status_code})")
            print(r.text)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_persistence()
