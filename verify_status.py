import requests
import json

BASE_URL = "http://localhost:8001/api/v1"

def test_status():
    symbol = "005930"
    url = f"{BASE_URL}/market-data/status/{symbol}"
    params = {"interval": "1m"}
    
    print(f"Testing GET {url} with params {params}")
    
    try:
        response = requests.get(url, params=params)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    test_status()
