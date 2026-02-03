
from backend.app.core.waterfall_engine import WaterfallBacktestEngine, BacktestContext
from backend.app.strategies.base import BaseStrategy

class MockStrategy(BaseStrategy):
    def on_data(self, candle):
        pass

engine = WaterfallBacktestEngine(MockStrategy)
context = BacktestContext({}, 1000000)

# Simulate some trades
trades = [
    {"type": "buy", "symbol": "005930", "price": 100, "quantity": 10, "time": "2024-01-01T10:00:00", "strategy_rank": 1},
    {"type": "sell", "symbol": "005930", "price": 110, "quantity": 10, "time": "2024-01-02T10:00:00", "strategy_rank": 1}
]
context.trades = trades

# Mock analyze trades call (this is where it crashes)
try:
    print("Running analyze_trades...")
    # timestamps are dummy strings
    result = engine._analyze_trades(trades, "2024-01-01T09:00:00", "2024-01-05T15:30:00", total_days=5)
    print("Success!")
    print(result)
except Exception as e:
    print(f"CRASHED: {e}")
    import traceback
    traceback.print_exc()
