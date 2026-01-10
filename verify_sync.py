
import sys
import os
from datetime import datetime

# Adjust path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.core.waterfall_engine import BacktestContext

def test_negative_cash():
    print("--- Testing Simulation Mode (Negative Cash) ---")
    
    # Setup Context with Low Capital
    feeds = {"TEST": [{"timestamp": "2024-01-01T09:00:00", "close": 2000}]}
    context = BacktestContext(feeds, initial_capital=1000, primary_symbol="TEST")
    
    # Attempt Buy (Cost 2000 > Capital 1000)
    print(f"Initial Cash: {context.cash}")
    context.buy("TEST", 1, price=2000)
    
    print(f"Post-Buy Cash: {context.cash}")
    print(f"Trades: {len(context.trades)}")
    
    # Assertions
    if len(context.trades) == 1 and context.cash == -1000:
        print("SUCCESS: Trade executed with negative cash.")
    else:
        print("FAILURE: Trade rejected or cash calc wrong.")
        sys.exit(1)

if __name__ == "__main__":
    test_negative_cash()
