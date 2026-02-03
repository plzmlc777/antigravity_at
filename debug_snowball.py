
import sys
import os
import asyncio
from datetime import datetime

# Adjust path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.core.waterfall_engine import BacktestContext, WaterfallBacktestEngine
from app.strategies.time_momentum import TimeMomentumStrategy

async def test_snowball():
    print("--- Testing Leverage Snowball (Day 1 -> Day 3) ---")
    
    # 1. Create Mock Feed (3 Days)
    # Day 1: Buy Signal (Rise), No Sell (Close high)
    # Day 2: Buy Signal (Rise), No Sell
    # Day 3: Buy Signal (Rise), End with CRASH
    
    feed = []
    
    # Day 1 (2024-01-01): Start 1000, Rise to 1050 (Buy), Close 1050 (Hold)
    feed.append({"timestamp": "2024-01-01T09:00:00", "open": 1000, "high": 1000, "low": 1000, "close": 1000, "volume": 100})
    feed.append({"timestamp": "2024-01-01T10:00:00", "open": 1050, "high": 1050, "low": 1050, "close": 1050, "volume": 100})
    # Missing 15:00 candle -> No sell logic triggers (unless Trailing Stop hit? Let's keep price steady)
    
    # Day 2 (2024-01-02): Start 1050, Rise to 1100 (Buy), Close 1100
    feed.append({"timestamp": "2024-01-02T09:00:00", "open": 1050, "high": 1050, "low": 1050, "close": 1050, "volume": 100})
    feed.append({"timestamp": "2024-01-02T10:00:00", "open": 1100, "high": 1100, "low": 1100, "close": 1100, "volume": 100})
    
    # Day 3 (2024-01-03): Start 1100, Rise to 1150 (Buy), CRASH to 500 at End
    feed.append({"timestamp": "2024-01-03T09:00:00", "open": 1100, "high": 1100, "low": 1100, "close": 1100, "volume": 100})
    feed.append({"timestamp": "2024-01-03T10:00:00", "open": 1150, "high": 1150, "low": 1150, "close": 1150, "volume": 100})
    # Crash
    feed.append({"timestamp": "2024-01-03T23:00:00", "open": 500, "high": 500, "low": 500, "close": 500, "volume": 100})

    # 2. Setup Engine
    engine = WaterfallBacktestEngine(TimeMomentumStrategy)
    
    # Config: Fixed Betting, 10M Capital, Target 2%
    strategies = [{
        "strategy": "time_momentum",
        "symbol": "TEST",
        "start_time": "09:00",
        "stop_time": "15:00",
        "delay_minutes": 10,
        "target_percent": 2.0,
        "betting_strategy": "fixed",
        "initial_capital": 10000000
    }]
    
    # 3. Initialize Context Manually (to inject specific feed)
    # We use a hack or just run the engine with a mock service?
    # Easier to replicate logic: Context + Strategy + Loop.
    
    feeds_map = {"TEST": feed}
    context = BacktestContext(feeds_map, initial_capital=10000000, primary_symbol="TEST")
    
    strategy = TimeMomentumStrategy(context, strategies[0])
    strategy.initialize()
    
    print(f"Initial Cash: {context.cash}")
    
    # 4. Run Loop
    for candle in feed:
        context.current_timestamp = candle['timestamp']
        print(f"\nProcessing {candle['timestamp']} | Price: {candle['close']}")
        strategy.on_data(candle)
        context.update_equity()
        
        current_holdings = context.holdings.get("TEST", 0)
        print(f"Holdings: {current_holdings} | Cash: {int(context.cash)} | Equity: {int(context.equity_curve[-1]['equity'])}")

    print("\n--- Final Analysis ---")
    print(f"Final Equity: {int(context.equity_curve[-1]['equity'])}")
    
    initial = 10000000
    final = context.equity_curve[-1]['equity']
    print(f"Return: {(final - initial)/initial*100:.2f}%")
    
    if current_holdings > 20000: # Typical buy is ~9500 per day. 20000 means 2x+
        print("CONFIRMED: Leverage Accumulation detected (> 20k shares).")
    else:
        print("RESULT: Normal Position Size.")

if __name__ == "__main__":
    asyncio.run(test_snowball())
