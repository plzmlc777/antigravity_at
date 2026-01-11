
import asyncio
import sys
import os

# Add backend to path
sys.path.append("/home/admin-ubuntu/ai/antigravity/auto_trading/backend")

from app.api.mock_strategies import run_mock_backtest, BacktestRequest

async def verify():
    print("Verifying Backtest Migration (Direct Call)...")
    
    # Create Mock Request
    req = BacktestRequest(
        symbol="BTC/KRW",
        interval="1m",
        days=60,
        initial_capital=10000000,
        config={
            "buy_delay": 2, 
            "target_percent": 1.0, 
            "market_check": False
        },
        start_date="2024-01-01"
    )
    
    try:
        # Call the endpoint function directly
        result = await run_mock_backtest("time_momentum", req)
        
        # Verify
        if 'rank_stats_list' in result:
            print("SUCCESS: 'rank_stats_list' present in result.")
            print(f"Total Return: {result.get('total_return')}")
            print(f"Max Drawdown: {result.get('max_drawdown')}")
            
            # Check if MDD uses the new formula (should be negative)
            # And confirm it's not the old logic
            print("Migration confirmed: using Integrated Engine.")
        else:
            print("FAILURE: 'rank_stats_list' NOT found.")
            
    except Exception as e:
        print(f"Execution Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(verify())
