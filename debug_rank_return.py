
from backend.app.core.waterfall_engine import WaterfallBacktestEngine, BacktestContext
from backend.app.strategies.base import BaseStrategy

class MockStrategy(BaseStrategy):
    def on_data(self, candle):
        pass

engine = WaterfallBacktestEngine(MockStrategy)
# Mocking an engine run context
initial_capital = 10000000 # 10 Million
trades = [
    {"type": "buy", "symbol": "005930", "price": 100, "quantity": 1000, "time": "2024-01-01T10:00:00", "strategy_rank": 1},
    {"type": "sell", "symbol": "005930", "price": 110, "quantity": 1000, "time": "2024-01-02T10:00:00", "strategy_rank": 1}
    # Profit = (110 - 100) * 1000 = 10,000 KRW
    # Return % = 10,000 / 10,000,000 * 100 = 0.1%
]

print("Running _calc_rank_stats check...")
try:
    # We call _analyze_trades which calls _calc_rank_stats
    result = engine._analyze_trades(trades, "2024-01-01", "2024-01-05", total_days=5, initial_capital=initial_capital)
    
    rank_stats = result['rank_stats_list']
    if not rank_stats:
        print("FAILED: No rank stats returned")
    else:
        r1 = rank_stats[0]
        print(f"Rank 1 Stats: {r1}")
        expected_return = 0.1
        if abs(r1['total_return'] - expected_return) < 0.001:
            print("SUCCESS: Total Return matches expected 0.1%")
        else:
            print(f"FAILED: Expected 0.1%, got {r1['total_return']}%")

except Exception as e:
    print(f"CRASHED: {e}")
    import traceback
    traceback.print_exc()
