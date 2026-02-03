import requests
import json

url = "http://localhost:8001/api/v1/strategies/time_momentum/backtest"
payload = {
    "symbol": "005930",
    "start_hour": 9,
    "delay_minutes": 10,
    "target_percent": 0.02,
    "safety_stop_percent": -0.03
}

try:
    print(f"Sending request to {url}...")
    res = requests.post(url, json=payload)
    print(f"Status: {res.status_code}")
    if res.status_code == 200:
        print("Success!")
        print(json.dumps(res.json(), indent=2)[:500] + "...")
    else:
        print("Failed!")
        print(res.text)
except Exception as e:
    print(f"Error: {e}")
