
import sys
import os
import asyncio
from datetime import datetime
from unittest.mock import MagicMock, patch

# Adjust path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.core.waterfall_engine import BacktestContext, WaterfallBacktestEngine
from app.strategies.base import BaseStrategy

async def test_master_clock():
    print("--- Testing Master Clock & Auto-Liquidation ---")
    
    # 1. Setup Feeds
    # Primary (Rank 1): Ends at 10:00 (Short)
    feed_primary = [
        {"timestamp": "2024-01-01T09:00:00", "open": 100, "high": 110, "low": 90, "close": 100, "volume": 100},
        {"timestamp": "2024-01-01T10:00:00", "open": 100, "high": 120, "low": 100, "close": 110, "volume": 100} 
    ]
    # Secondary (Rank 2): Ends at 11:00 (Longer)
    feed_secondary = [
        {"timestamp": "2024-01-01T09:00:00", "open": 50, "high": 55, "low": 45, "close": 50, "volume": 100},
        {"timestamp": "2024-01-01T10:00:00", "open": 50, "high": 60, "low": 50, "close": 55, "volume": 100},
        {"timestamp": "2024-01-01T11:00:00", "open": 55, "high": 65, "low": 55, "close": 60, "volume": 100} 
    ]
    
    strategies = [
        {"symbol": "P", "strategy": "mock", "rank": 1}, 
        {"symbol": "S", "strategy": "mock", "rank": 2}
    ]
    
    # Define Mock Data Service logic
    async def mock_get_candles(self, symbol, **kwargs):
        if symbol == "P": return feed_primary
        if symbol == "S": return feed_secondary
        return []

    # Mock Strategy that Buys on first candle
    class BuyStrategy(BaseStrategy):
        def on_data(self, data):
            # Buy 1 unit if not held
            sym = self.config['symbol']
            # Simple 1 unit buy logic
            if self.context.holdings.get(sym, 0) == 0:
                self.context.buy(sym, 1)

    # Patch the MarketDataService class
    with patch('app.services.market_data.MarketDataService') as MockServiceClass:
        # Configuration the mock instance
        mock_instance = MockServiceClass.return_value
        mock_instance.get_candles.side_effect = mock_get_candles
        
        # Initialize Engine with BuyStrategy
        engine = WaterfallBacktestEngine(BuyStrategy)
        
        print("Running Integrated Backtest...")
        result = await engine.run_integrated(
            strategies_config=strategies,
            global_symbol="P",
            initial_capital=1000
        )
    
        print("\n--- Analysis ---")
        logs = result['logs']
        
        # Check Liquidation Log
        liquidation_logs = [l for l in logs if "AUTO-LIQUIDATION" in str(l)]
        print(f"Liquidation Logs: {liquidation_logs}")
        
        if not liquidation_logs:
            print("FAILURE: Auto-Liquidation did not trigger.")
            return
        
        # Check if S was liquidated at 55 (End of Primary at 10:00) 
        # S Price at 10:00 is 55.
        # If loop went to 11:00, S price is 60.
        
        lid_s = next((l for l in liquidation_logs if "S" in l), "")
        if "at 55" in lid_s or "at 55.0" in lid_s:
             print("SUCCESS: Validated Master Clock cutoff (S sold at 55).")
        elif "at 60" in lid_s:
             print("FAILURE: Simulation ran past Primary End (S sold at 60).")
        else:
             print(f"FAILURE: Unexpected liquidation price for S. Log: {lid_s}")

if __name__ == "__main__":
    asyncio.run(test_master_clock())
