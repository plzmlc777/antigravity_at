
import asyncio
import uuid
from backend.app.core.live_context import LiveContext
from backend.app.adapters.kiwoom_real import KiwoomRealAdapter
from backend.app.db.session import SessionLocal
from backend.app.models.live_trading import LiveBotSession, LiveTradeExecution, ExecutionStatus
from datetime import datetime

# MOCK ADAPTER
class MockKiwoomAdapter(KiwoomRealAdapter):
    def __init__(self):
        self.calls = []
        
    async def get_balance(self):
        return {"cash": {"KRW": 1000000}, "holdings": {}}
        
    async def place_buy_order(self, symbol, price, quantity):
        self.calls.append(("BUY", symbol, quantity))
        return {"status": "success", "order_no": "MOCK_ORD_1"}
        
    async def place_sell_order(self, symbol, price, quantity):
        self.calls.append(("SELL", symbol, quantity))
        return {"status": "success", "order_no": "MOCK_ORD_2"}

async def verify_context():
    print("--- Verifying Live Context ---")
    
    # Setup DB Session
    db = SessionLocal()
    session_id = str(uuid.uuid4())
    sess = LiveBotSession(id=session_id, symbol="TEST", strategy_name="Test", strategy_config={}, interval="1m")
    db.add(sess)
    db.commit()
    db.close()
    
    adapter = MockKiwoomAdapter()
    ctx = LiveContext(session_id, adapter, initial_capital=1000000)
    
    # 1. Update Price
    ctx.price_map = {"TEST": 1000}
    
    # 2. Trigger Signal (Sync)
    print("Triggering BUY Signal...")
    ctx.buy("TEST", 10)
    
    # Check DB
    db = SessionLocal()
    pending = db.query(LiveTradeExecution).filter_by(session_id=session_id, status=ExecutionStatus.PENDING).all()
    assert len(pending) == 1
    assert pending[0].requested_quantity == 10
    assert pending[0].symbol == "TEST"
    print("DB Verification (PENDING): PASS")
    db.close()
    
    # 3. Process Queue (Async)
    print("Processing Queue...")
    await ctx.process_queue()
    
    # Check Adapter Calls
    assert len(adapter.calls) == 1
    assert adapter.calls[0] == ("BUY", "TEST", 10)
    print("Adapter Call Verification: PASS")
    
    # Check DB Update
    db = SessionLocal()
    submitted = db.query(LiveTradeExecution).filter_by(session_id=session_id, status=ExecutionStatus.SUBMITTED).all()
    assert len(submitted) == 1
    print("DB Verification (SUBMITTED): PASS")
    db.close()
    
    print("LIVE CONTEXT VERIFICATION PASSED")

if __name__ == "__main__":
    asyncio.run(verify_context())
