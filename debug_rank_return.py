
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
    {"type": "sell", "symbol": "005930", "price": 110, "quantity": 1000, "time": "2024-01-02T10:00:00", "strategy_rank": 1},
    # Trade 1: +10,000 KRW. Cum: +10,000. Peak: +10,000.
    
    {"type": "buy", "symbol": "005930", "price": 100, "quantity": 1000, "time": "2024-01-03T10:00:00", "strategy_rank": 1},
    {"type": "sell", "symbol": "005930", "price": 95, "quantity": 1000, "time": "2024-01-04T10:00:00", "strategy_rank": 1}
    # Trade 2: -5,000 KRW. Cum: +5,000. Peak: +10,000.
    # Drawdown Amount: 5,000 KRW.
    # MDD % = -(5,000 / 10,000,000 * 100) = -0.05%
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
        
        # Check Total Return (Net +5000 / 10M = 0.05%)
        if abs(r1['total_return'] - 0.05) < 0.001:
            print("SUCCESS: Total Return matches expected 0.05%")
        else:
            print(f"FAILED: Expected Return 0.05%, got {r1['total_return']}%")
            
        # Check MDD (-0.05%)
        if abs(r1['max_drawdown'] - (-0.05)) < 0.001:
             print("SUCCESS: Max Drawdown matches expected -0.05%")
        else:
             print(f"FAILED: Expected MDD -0.05%, got {r1['max_drawdown']}%")

except Exception as e:
    print(f"CRASHED: {e}")
    import traceback
    traceback.print_exc()
