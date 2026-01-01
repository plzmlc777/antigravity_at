import sys
import os
import asyncio
from datetime import datetime, timedelta

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.strategies.time_momentum import TimeMomentumStrategy
from app.core.backtest_engine import BacktestEngine

async def run_debug():
    config = {
        "start_time": "09:00",
        "direction": "fall",
        "target_percent": 0.5,
        "stop_loss": 5,
        "betting_mode": "fixed",
        "initial_capital": 10000000
    }
    
    # Mock some data via strategy (or just let engine fetch mock)
    # Engine defaults to fetching from DB/Mock.
    # We rely on existing adapters.
    
    print("Initializing Engine...")
    engine = BacktestEngine(TimeMomentumStrategy, config)
    
    print("Running Backtest...")
    # Use a symbol that likely has data or mock
    result = await engine.run(
        symbol="005930",
        interval="1m",
        duration_days=5,
        from_date="2024-01-01",
        initial_capital=10000000
    )
    
    print("\n--- Result Keys ---")
    for k in result.keys():
        print(f"{k}: {type(result[k])} = {result[k] if not isinstance(result[k], (list, dict)) else '...'}")
        
    print("\n--- Check Specifics ---")
    print(f"Acceleration Score: {result.get('acceleration_score')}")
    print(f"Stability Score: {result.get('stability_score')}")

if __name__ == "__main__":
    asyncio.run(run_debug())
