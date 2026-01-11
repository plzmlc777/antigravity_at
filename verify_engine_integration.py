
import asyncio
import sys
from datetime import datetime

sys.path.append("/home/admin-ubuntu/ai/antigravity/auto_trading/backend")

from app.core.waterfall_engine import BacktestContext

def verify_integration():
    print("=== BacktestContext Order Integration Verification ===")
    
    # 1. Setup Context with Dummy Data
    feeds = {
        "TEST": [
            {"timestamp": "2024-01-01T09:00:00", "open": 100, "high": 110, "low": 90, "close": 105}
        ]
    }
    context = BacktestContext(feeds, initial_capital=100000)
    
    # 2. Test Buy (Should use StockOrder internally)
    print("\n1. Testing BUY...")
    trade = context.buy("TEST", 10, price=100)
    
    if trade.get('status') == 'failed':
        print(f"FAILURE: Buy failed. Reason: {trade.get('reason')}")
    else:
        print(f"SUCCESS: Buy executed. Trade: {trade}")
        # Check if 'order_id' exists (added by new logic)
        if 'order_id' in trade:
            print(f"   StockOrder Integration Confirmed (Order ID: {trade['order_id']})")
        else:
            print("   WARNING: 'order_id' missing. Old logic might be running?")

    # 3. Test Sell
    print("\n2. Testing SELL...")
    trade_sell = context.sell("TEST", 5, price=110)
    
    if trade_sell.get('status') == 'failed':
         print(f"FAILURE: Sell failed. Reason: {trade_sell.get('reason')}")
    else:
        print(f"SUCCESS: Sell executed. Trade: {trade_sell}")
        if 'order_id' in trade_sell:
             print(f"   StockOrder Integration Confirmed (Order ID: {trade_sell['order_id']})")

if __name__ == "__main__":
    verify_integration()
