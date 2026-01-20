
import sys
import os
from datetime import datetime, timedelta

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.services.stats_service import StatsService

class MockTrade:
    def __init__(self, pnl, exit_time, entry_time=None, pnl_percent=0.0, holding_seconds=0):
        self.pnl = pnl
        self.exit_time = exit_time
        self.entry_time = entry_time or (exit_time - timedelta(minutes=15))
        self.pnl_percent = pnl_percent
        self.holding_seconds = holding_seconds

def test_trade_based_stats():
    print("Running Verification: Trade-based Stats...")
    
    # 1. Setup mock trades
    # Start: 1,000,000
    # Trade 1: +10,000 -> 1,010,000
    # Trade 2: -5,000  -> 1,005,000
    # Trade 3: +15,000 -> 1,020,000
    
    now = datetime.now()
    trades = [
        MockTrade(10000, now - timedelta(minutes=30), pnl_percent=0.01),
        MockTrade(-5000, now - timedelta(minutes=20), pnl_percent=-0.005),
        MockTrade(15000, now - timedelta(minutes=10), pnl_percent=0.015)
    ]
    
    initial_capital = 1000000
    
    # 2. Calculate stats
    # equity_curve is now ignored for primary calcs but passed for signature compatibility
    stats = StatsService.calculate_detailed_stats(trades, [], start_time=now - timedelta(hours=1), initial_capital=initial_capital)
    
    print(f"Calculated Stats: {stats}")
    
    # 3. Assertions
    # Total Profit = 10000 - 5000 + 15000 = 20000
    # Total Return = 20000 / 1000000 * 100 = 2.00%
    assert stats["total_return"] == "2.00%"
    
    # Max Drawdown: 
    # Peak 1: 1,010,000
    # Dip 1: 1,005,000 (DD = (1,010,000 - 1,005,000) / 1,010,000 = 0.495%)
    # Max DD should be approx 0.50% (displayed as -0.50%)
    assert stats["max_drawdown"] == "-0.50%"
    
    # Win Rate: 2 wins / 3 trades = 66.7%
    assert stats["win_rate"] == "66.7%"
    
    # Profit Factor: Gross Profit (25000) / Gross Loss (5000) = 5.00
    assert stats["profit_factor"] == "5.00"
    
    print("\nVerification PASS: Virtual equity curve correctly derived from trades.")

if __name__ == "__main__":
    test_trade_based_stats()
