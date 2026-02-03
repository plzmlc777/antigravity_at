import asyncio
import sys
import os
from datetime import datetime, timedelta

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from backend.app.core.waterfall_engine import WaterfallBacktestEngine
from backend.app.core.backtest_engine import BacktestContext

# Mock Data Service
from backend.app.services.market_data import MarketDataService

async def mock_get_candles(self, symbol, interval, days):
    print(f"Mock Fetch: {symbol} at {interval}")
    now = datetime.now()
    candles = []
    delta = timedelta(minutes=15) if interval == '15m' else timedelta(minutes=1)
    
    for i in range(10):
        t = now - (delta * (10 - i))
        candles.append({
            'timestamp': t.isoformat(),
            'open': 100, 'high': 110, 'low': 90, 'close': 105, 'volume': 1000
        })
    return candles

MarketDataService.get_candles = mock_get_candles

async def verify():
    print("Starting Verification for Task 1...")
    
    # Minimal Mock Strategy Class
    class MockStrategy:
        def __init__(self, context, config=None):
            self.context = context
            self.config = config or {}
        def initialize(self): pass
        def on_data(self, candle): pass

    engine = WaterfallBacktestEngine(MockStrategy) 

    # Config: Rank 1 (1m), Rank 2 (15m)
    strategies_config = [
        {'symbol': 'KRW-BTC', 'interval': '1m'},
        {'symbol': 'KRW-ETH', 'interval': '15m'}
    ]

    try:
        result = await engine.run_integrated(
            strategies_config=strategies_config,
            global_symbol='KRW-BTC',
            interval='1m' # Global default
        )
        
        print("Backtest Finished.")
        
        # Check Multi-OHLCV Data
        multi = result.get('multi_ohlcv_data', {})
        print(f"Multi-OHLCV Keys: {list(multi.keys())}")
        
        if 'KRW-BTC' in multi and 'KRW-ETH' in multi:
            print("SUCCESS: Both symbols data present.")
        else:
            print("FAILURE: Missing symbol data.")
            
        # Check Chart Data
        if 'chart_data' in result:
             print("SUCCESS: chart_data is present.")
        else:
             print("FAILURE: chart_data is missing.")
             
    except Exception as e:
        print(f"CRASH: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(verify())
