import sys
import os
# Add backend to path
sys.path.append("/home/admin-ubuntu/ai/antigravity/auto_trading/backend")

try:
    from app.strategies.time_momentum import TimeMomentumStrategy
    from app.strategies.base import IContext
except ImportError:
    # Try alternate path if generic fallback
    sys.path.append("/home/admin-ubuntu/ai/antigravity/auto_trading")
    from backend.app.strategies.time_momentum import TimeMomentumStrategy
    from backend.app.strategies.base import IContext

class MockContext(IContext):
    def get_time(self): return None
    def get_current_price(self, s): return 0
    def buy(self, s, q, p=0, t="market"): pass
    def sell(self, s, q, p=0, t="market"): pass
    def log(self, m): print(m)
    @property
    def current_candle(self): return {}
    def update_equity(self): pass

try:
    print("Testing TimeMomentumStrategy initialization with empty delay...")
    config = {"delay_minutes": ""}
    strategy = TimeMomentumStrategy(MockContext(), config)
    strategy.initialize()
    print("Success: Delay minutes =", strategy.delay_minutes)
    
    print("Testing with ALL empty...")
    config = {
        "start_time": "", "stop_time": "", "delay_minutes": "",
        "target_percent": "", "safety_stop_percent": "",
        "trailing_start_percent": "", "trailing_stop_drop": ""
    }
    strategy = TimeMomentumStrategy(MockContext(), config)
    strategy.initialize()
    print("Success: All empty handled.")

    print("Testing with None...")
    config = {
        "start_time": None, "delay_minutes": None
    }
    strategy = TimeMomentumStrategy(MockContext(), config)
    strategy.initialize()
    print("Success: None handled.")
    
except Exception as e:
    import traceback
    traceback.print_exc()
    print("Failed")
