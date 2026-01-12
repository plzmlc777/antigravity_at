
import asyncio
import sys
import os

# Add project root to path
sys.path.append("/home/admin-ubuntu/ai/antigravity/auto_trading/backend")

from app.core.waterfall_engine import WaterfallBacktestEngine
from app.strategies.base import BaseStrategy

class DummyStrategy(BaseStrategy):
    def initialize(self):
        self.entry_price = 0
        
    def on_data(self, candle):
        # Simple Buy & Hold Logic to generate some trades/data
        if self.entry_price == 0:
            self.entry_price = candle['close']
            self.buy(self.config.get('symbol'), 1, candle['close'])
        
        # Sell at end (handled by engine force close usually, or we can explicit sell)
        pass

async def main():
    print("--- Verifying Optimization Light Mode ---")
    
    config = {"symbol": "BTC-USD-15m", "interval": "15m"} # Use a known symbol if possible or mock
    # Wait, fetching real data might fail if network/db issue. 
    # Let's rely on MarketDataService returning something or Mock it.
    # Actually, Waterfall uses MarketDataService. 
    # For verification, we can try running with a symbol we know exists or handle empty.
    
    engine = WaterfallBacktestEngine(DummyStrategy, config)
    
    print("Running integrated backtest with optimize_mode=True...")
    try:
        result = await engine.run_integrated(
            strategies_config=[config],
            global_symbol="BTC-USD-15m", # Assuming this exists or will return empty
            duration_days=5,
            optimize_mode=True
        )
    except Exception as e:
        print(f"Execution Error: {e}")
        return

    # keys to check
    empty_keys = ["chart_data", "ohlcv_data", "decile_stats"]
    zero_keys = ["stability_score", "acceleration_score"]
    
    print("\n[Assertions]")
    
    # Check Empty Lists
    for k in empty_keys:
        val = result.get(k)
        if isinstance(val, list) and len(val) == 0:
            print(f"PASS: {k} is empty list.")
        elif isinstance(val, dict) and len(val) == 0: # multi_ohlcv_data
             print(f"PASS: {k} is empty dict.")
        else:
            print(f"FAIL: {k} should be empty but is {type(val)}: {len(val) if hasattr(val, '__len__') else val}")

    # Check Zero Values
    for k in zero_keys:
        val = result.get(k)
        if val == 0.0 or val == 0:
            print(f"PASS: {k} is zero.")
        else:
            print(f"FAIL: {k} should be zero but is {val}")
            
    # Check Core Stats exist (even if 0 due to no data, keys must exist)
    if "total_return" in result:
        print(f"PASS: total_return is present: {result['total_return']}")
    else:
        print("FAIL: total_return missing")
        
    if "rank_stats_list" in result:
        print(f"PASS: rank_stats_list is present (length {len(result['rank_stats_list'])})")
    else:
        print("FAIL: rank_stats_list missing")

    if result.get("logs") and len(result["logs"]) > 0:
        if result["logs"][0] == "No data collected":
             print("WARNING: Test ran with NO DATA. Assertions on empty/zero might be trivial.")
        else:
             print("INFO: Test ran with actual data.")

if __name__ == "__main__":
    asyncio.run(main())
