import asyncio
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath("/home/admin-ubuntu/ai/antigravity/auto_trading/backend"))

from app.core.backtest_engine import BacktestEngine
from app.strategies.time_momentum import TimeMomentumStrategy

async def test_legacy_single():
    print("\n--- Testing Single Symbol (Legacy) ---")
    engine = BacktestEngine(TimeMomentumStrategy)
    
    # Single usage
    results = await engine.run(
        symbol="005930", 
        duration_days=5, 
        interval="1m"
    )
    print(f"Single Symbol Logs: {len(results.get('logs', []))} entries")
    # print('\n'.join(results.get('logs', [])[:5]))
    print(f"Total Return: {results.get('total_return')}")
    print(f"Activity Rate: {results.get('activity_rate')}")

async def test_multi_symbol():
    print("\n--- Testing Multi Symbol (Priority) ---")
    engine = BacktestEngine(TimeMomentumStrategy)
    
    # Multi usage
    # Config 1: SEC (High Target, unlikely to trade?)
    # Config 2: SKh (Low Target, likely to trade)
    # We will use same symbol twice for testing if we don't have others, 
    # but ideally different params.
    
    configs = [
        {
            "symbol": "005930", # SEC
            "start_time": "09:00",
            "delay_minutes": 10,
            "target_percent": 10.0, # Impossible 10% target in 10 mins
            "direction": "rise"
        },
        {
            "symbol": "005930", # SEC (Reuse for data availability)
            "start_time": "09:00",
            "delay_minutes": 11, # Check 1 min later
            "target_percent": 0.1, # Easy 0.1% target
            "direction": "rise"
        }
    ]
    
    results = await engine.run(
        configs=configs,
        duration_days=5,
        interval="1m"
    )
    
    print(f"Multi Symbol Logs: {len(results.get('logs', []))} entries")
    logs = results.get('logs', [])
    for log in logs:
        if "BUY" in log:
            print(log)
            
    print(f"Total Return: {results.get('total_return')}")
    print(f"Activity Rate: {results.get('activity_rate')}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_legacy_single())
    loop.run_until_complete(test_multi_symbol())
