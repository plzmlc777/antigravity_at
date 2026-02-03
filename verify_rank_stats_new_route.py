import requests
import json

url = "http://localhost:8001/api/v1/strategies/integrated/v2-backtest-new"
payload = {
    "initial_capital": 10000000,
    "from_date": "2024-01-01T00:00:00",
    "configs": [
        {
            "strategy": "Time Momentum",
            "symbol": "005930",
            "interval": "1m",
            "params": {"momentum_window": 20}
        },
        {
            "strategy": "Time Momentum",
            "symbol": "000660",
            "interval": "1m",
            "params": {"momentum_window": 20}
        }
    ]
}

print(f"Sending POST request to {url}...")
try:
    response = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
    
    if response.status_code == 200:
        print("Response received successfully.")
        data = response.json()
        
        if 'rank_stats_list' in data:
            print("✅ 'rank_stats_list' field FOUND in response.")
            print(f"Content of 'rank_stats_list' (Length: {len(data['rank_stats_list'])}):")
            print(json.dumps(data['rank_stats_list'], indent=2))
            
            if len(data['rank_stats_list']) > 0:
                print("✅ 'rank_stats_list' contains data!")
            else:
                print("⚠️ 'rank_stats_list' is empty.")
        else:
            print("❌ 'rank_stats_list' field NOT FOUND in response.")
            print("Keys found:", list(data.keys()))
            
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)

except Exception as e:
    print(f"❌ Request failed: {e}")
