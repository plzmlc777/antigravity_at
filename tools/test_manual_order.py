import requests
import json
import sys

BASE_URL = "http://localhost:8000/api/v1"

def log(msg):
    print(f"[TEST] {msg}")

def test_status():
    try:
        resp = requests.get(f"{BASE_URL}/status")
        log(f"Status check: {resp.status_code} {resp.json()}")
    except Exception as e:
        log(f"Status check failed: {e}")
        sys.exit(1)

def test_manual_buy_qty():
    payload = {
        "symbol": "005930",
        "order_type": "buy",
        "price": 70000,
        "mode": "quantity",
        "quantity": 10
    }
    resp = requests.post(f"{BASE_URL}/order/manual", json=payload)
    if resp.status_code == 200:
        log(f"Buy Qty Test: PASS - {resp.json()}")
    else:
        log(f"Buy Qty Test: FAIL - {resp.text}")

def test_manual_buy_amount():
    # Buy 200,000 KRW worth of stock at 50,000 KRW/share -> 4 shares
    payload = {
        "symbol": "000660",
        "order_type": "buy",
        "price": 50000,
        "mode": "amount",
        "amount": 200000
    }
    resp = requests.post(f"{BASE_URL}/order/manual", json=payload)
    data = resp.json()
    if resp.status_code == 200 and data.get("quantity") == 4:
        log(f"Buy Amount Test: PASS - {data}")
    else:
        log(f"Buy Amount Test: FAIL - {resp.text}")

def test_manual_buy_percent():
    # Buy with 10% of cash
    # Need to know balance first to verify, but for now just check if API accepts it
    payload = {
        "symbol": "005930",
        "order_type": "buy",
        "price": 10000,
        "mode": "percent_cash",
        "percent": 0.1
    }
    resp = requests.post(f"{BASE_URL}/order/manual", json=payload)
    if resp.status_code == 200:
        log(f"Buy Percent Test: PASS - {resp.json()}")
    else:
        log(f"Buy Percent Test: FAIL - {resp.text}")

def test_manual_market_buy_qty():
    payload = {
        "symbol": "005930",
        "order_type": "buy",
        "price_type": "market",
        "price": 0,
        "mode": "quantity",
        "quantity": 5
    }
    resp = requests.post(f"{BASE_URL}/order/manual", json=payload)
    if resp.status_code == 200:
        log(f"Market Buy Qty Test: PASS - {resp.json()}")
    else:
        log(f"Market Buy Qty Test: FAIL - {resp.text}")

def test_manual_market_buy_amount():
    # Buy 200,000 KRW worth of stock at Market Price
    payload = {
        "symbol": "000660",
        "order_type": "buy",
        "price_type": "market",
        "price": 0,
        "mode": "amount",
        "amount": 200000
    }
    resp = requests.post(f"{BASE_URL}/order/manual", json=payload)
    if resp.status_code == 200:
        # Check if executed price is non-zero (mock should return price)
        data = resp.json()
        if data.get("price", 0) > 0 and data.get("quantity", 0) > 0:
            log(f"Market Buy Amount Test: PASS - {data}")
        else:
             log(f"Market Buy Amount Test: WARN - Executed, but check price/qty: {data}")
    else:
        log(f"Market Buy Amount Test: FAIL - {resp.text}")

if __name__ == "__main__":
    log("Starting Manual Order Tests...")
    test_status()
    test_manual_buy_qty()
    test_manual_market_buy_qty()
    test_manual_market_buy_amount()
    log("Tests Completed.")
