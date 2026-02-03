
import asyncio
import sys
import os

# Ensure backend acts as package
sys.path.append("/home/admin-ubuntu/ai/antigravity/auto_trading/backend")

from app.api.mock_strategies import _run_sync_in_process

# Mock Strategy for test
class MockStrategy:
    def __init__(self, context, config): pass
    def initialize(self): pass
    def on_data(self, data): pass

def verify_optimization():
    print("=== Optimization Engine Migration Verification ===")
    
    # 1. Config
    config = {
        "target_percent": 1.0, 
        "loss_cut_percent": 3.0,
        "market_check": False
    }
    
    # 2. Run Sync (Direct call as if inside worker process)
    # Using 'TEST' symbol which might have mock data from previous tests or will fail if no data.
    # We rely on WaterfallEngine handling empty data gracefully.
    
    try:
        conf_out, result = _run_sync_in_process(
            strategy_cls=MockStrategy,
            config=config,
            symbol="TEST_OPT",
            interval="1m",
            days=1,
            from_date=None,
            initial_capital=10000000
        )
        
        print("\nExecution Result:")
        # print(result)
        
        # 3. Validation
        if "error" in result:
             # It might fail due to no data, which is expected for 'TEST_OPT'
             # But if it fails with "ImportError" or "AttributeError", that's a bug.
             print(f"Result returned error: {result['error']}")
             
             if "No data" in str(result['error']) or "No Simulation data" in str(result.get('logs', [])):
                 print("SUCCESS: Engine ran and reported No Data (Expected for dummy symbol).")
             else:
                 print("WARNING: Unexpected error type.")
        else:
             # If it somehow got data (e.g. if we used a real symbol)
             print("SUCCESS: Engine ran successfully.")
             if 'rank_stats_list' in result:
                 print("CONFIRMED: Output contains 'rank_stats_list', verifying WaterfallEngine usage.")
             else:
                 print("FAILURE: 'rank_stats_list' missing. Old engine might be active.")
                 
    except Exception as e:
        print(f"CRITICAL FAILURE: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_optimization()
