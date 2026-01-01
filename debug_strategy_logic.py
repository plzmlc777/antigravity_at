
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List
import sys
import os

# Add path to allow imports
sys.path.append(os.getcwd())

# Mock Classes
class MockContext:
    def __init__(self):
        self.logs = []
        self.cash = 10000000
        self.holdings = {}
        self.current_time = None

    def get_time(self):
        return self.current_time

    def log(self, msg):
        self.logs.append(f"[{self.current_time}] {msg}")
        print(f"[{self.current_time}] {msg}")

    def buy(self, symbol, qty):
        self.log(f"BUY {symbol} {qty}")
        self.holdings[symbol] = qty

    def sell(self, symbol, qty):
        self.log(f"SELL {symbol} {qty}")
        if symbol in self.holdings:
            del self.holdings[symbol]

# Import Strategy
# We need to simulate the file import or copy the class. 
# Since we modified the file, we should import it.
from backend.app.strategies.time_momentum import TimeMomentumStrategy

def generate_data():
    # Generate 2 days of data
    # Day 1: Normal 09:00 start
    # Day 2: Late 09:01 start
    data = []
    
    # Day 1
    base = datetime(2024, 1, 1, 9, 0, 0)
    for i in range(380): # Until 15:20
        t = base + timedelta(minutes=i)
        data.append({
            "timestamp": t,
            "close": 10000,
            "high": 10000,
            "low": 10000,
            "open": 10000,
            "volume": 100
        })

    # Day 2 (Starts 09:01)
    base = datetime(2024, 1, 2, 9, 1, 0)
    for i in range(380):
        t = base + timedelta(minutes=i)
        data.append({
            "timestamp": t,
            "close": 10000, # Flat price
            "high": 10000,
            "low": 10000,
            "open": 10000,
            "volume": 100
        })
        
    return data

def run_test():
    ctx = MockContext()
    config = {
        "start_time": "09:00",
        "delay_minutes": 60,
        "direction": "fall",
        "target_percent": 0, # Should trigger on flat price
        "stop_time": "15:00",
        "initial_capital": 10000000
    }
    
    strategy = TimeMomentumStrategy(ctx, config)
    strategy.initialize()
    
    data = generate_data()
    
    print("--- STARTING SIMULATION ---")
    for candle in data:
        ctx.current_time = candle['timestamp']
        strategy.on_data(candle)

if __name__ == "__main__":
    run_test()
