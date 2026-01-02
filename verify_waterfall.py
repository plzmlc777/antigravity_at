import asyncio
import os
import sys
from unittest.mock import MagicMock
from datetime import datetime, timedelta

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.core.backtest_engine import BacktestEngine
from app.strategies.time_momentum import TimeMomentumStrategy

# Mock Data Generator
def generate_mock_candles(days=1):
    candles = []
    base_price = 100.0
    start_time = datetime.strptime("2024-01-01 09:00:00", "%Y-%m-%d %H:%M:%S")
    
    # Create 1 day of 1m data (60*24 = 1440 candles)
    # We will simulate a +5% jump at 09:10 to trigger the strategy
    for i in range(1440 * days):
        curr_time = start_time + timedelta(minutes=i)
        
        # At 09:10, Jump price by 5%
        if curr_time.time() >= datetime.strptime("09:10", "%H:%M").time() and curr_time.time() < datetime.strptime("09:15", "%H:%M").time():
             close_price = base_price * 1.05
        else:
             close_price = base_price
             
        candles.append({
            "timestamp": curr_time.isoformat(),
            "open": base_price,
            "high": max(base_price, close_price) + 1,
            "low": min(base_price, close_price) - 1,
            "close": close_price,
            "volume": 1000
        })
    return candles

async def test_integrated_backtest():
    print("--- Starting MOCK Verification ---")
    
    # Mock MarketDataService
    mock_feed = generate_mock_candles(days=2)
    
    # We need to Monkey Patch or Mock the MarketDataService used inside backtest_engine
    # Since it's imported INSIDE the method run_integrated_simulation...
    # import ..services.market_data as md_module -> we can patch sys.modules?
    # Or cleaner: Modify the engine method? No.
    # Patching sys.modules['app.services.market_data']
    
    import app.services.market_data
    mock_service = MagicMock()
    mock_service.get_candles.return_value = mock_feed
    
    # Patch the class instantiated inside the method
    import app.services.market_data
    
    async def async_get_candles(*args, **kwargs):
        print(f"Mock fetching for {args[0] if args else 'symbol'}...")
        return mock_feed

    mock_service_instance = MagicMock()
    mock_service_instance.get_candles = async_get_candles
    
    app.services.market_data.MarketDataService = MagicMock(return_value=mock_service_instance)
    
    engine = BacktestEngine(TimeMomentumStrategy)
    
    # Config A: Strict (2%) - Should trigger because we have 5% jump
    config_strict = [{
        "strategy": "time_momentum",
        "symbol": "KRW-BTC",
        "interval": "1m",
        "start_time": "09:00",
        "delay_minutes": 10,
        "target_percent": 2.0, 
        "betting_strategy": "fixed",
        "initial_capital": 10000000
    }]
    
    print("\n[Test 1] Mock Data + Strict (2%) Target...")
    res_strict = await engine.run_integrated_simulation(
        strategies_config=config_strict,
        symbol="KRW-BTC",
        duration_days=2, 
        initial_capital=10000000
    )
    
    trade_count = len(res_strict.get("trades", [])) if "trades" in res_strict else 0
    # Actually backtest engine generates stats charts, not raw trades list in return usually?
    # Let's inspect logs for "Entry Triggered"
    trigger_count = sum(1 for l in res_strict.get("logs", []) if "Entry Triggered" in l)
    
    print(f"Total Return: {res_strict['total_return']}")
    print(f"Trigger Count: {trigger_count}")
    
    if trigger_count > 0:
        print("SUCCESS: Strategy Logic works correctly with valid data satisfying conditions.")
    else:
        print("FAILURE: Strategy Logic failed even with +5% jump data.")
        print("Logs:", res_strict.get("logs", [])[:10])

if __name__ == "__main__":
    asyncio.run(test_integrated_backtest())
