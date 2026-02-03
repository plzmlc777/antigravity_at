
import asyncio
import sys
import os

# Ensure backend acts as package
sys.path.append("/home/admin-ubuntu/ai/antigravity/auto_trading/backend")

from app.models.new_orders import StockOrder, OrderExecutor, OrderSide, OrderType, OrderStatus
from app.adapters.kiwoom_mock import KiwoomMockAdapter

async def verify_poc():
    print("=== Order Class System POC Verification ===")
    
    # 1. Setup Environment
    # Use existing Mock Adapter
    adapter = KiwoomMockAdapter()
    executor = OrderExecutor(adapter)
    
    # 2. Create an Order Object
    # e.g. Buy 10 Samsung Electronics @ 70,000
    order = StockOrder(
        symbol="005930", 
        side=OrderSide.BUY, 
        quantity=10, 
        price=70000, 
        order_type=OrderType.LIMIT
    )
    
    print(f"1. Order Created: {order.to_dict()}")
    
    # 3. Execute Order
    print("\n2. Executing Order via Executor...")
    await executor.execute(order)
    
    print(f"3. Order Status After Execution: {order.status}")
    print(f"   Exchange ID: {order.exchange_order_id}")
    
    if order.status == OrderStatus.PENDING or order.exchange_order_id:
        print("SUCCESS: Order transmitted successfully.")
    else:
        print(f"FAILURE: Order rejected. Msg: {order.message}")
        
    # 4. Simulate Fill (Update State)
    print("\n4. Simulating Fill update...")
    order.add_fill(fill_price=70000, fill_qty=5) # Partial
    print(f"   Status: {order.status}, Filled: {order.filled_quantity}")
    
    order.add_fill(fill_price=70100, fill_qty=5) # Complete
    print(f"   Status: {order.status}, Filled: {order.filled_quantity}, Avg Price: {order.avg_fill_price}")

    if order.status == OrderStatus.FILLED:
        print("SUCCESS: Order lifecycle completed.")
    else:
        print("FAILURE: Order lifecycle incorrect.")

if __name__ == "__main__":
    asyncio.run(verify_poc())
