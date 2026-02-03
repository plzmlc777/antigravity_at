import requests
import json

BASE_URL = "http://localhost:8001/api/v1"

def test_fetch_market_data():
    symbol = "085310"
    url = f"{BASE_URL}/market-data/fetch/{symbol}"
    payload = {
        "interval": "1m",
        "days": 3650
    }
    
    print(f"Testing POST {url} with payload {payload}")
    
    try:
        response = requests.post(url, json=payload)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("SUCCESS: Backend accepted the request.")
        else:
            print("FAILURE: Backend rejected the request.")
            
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    test_fetch_market_data()
