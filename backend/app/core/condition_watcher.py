import asyncio
import logging
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..db.session import SessionLocal
from ..models.condition import ConditionalOrder, ConditionType, ConditionStatus
from ..adapters.kiwoom_real import KiwoomRealAdapter
from ..adapters.kiwoom_mock import KiwoomMockAdapter
from ..core.config import settings

logger = logging.getLogger("ConditionWatcher")

class ConditionWatcher:
    def __init__(self):
        self.is_running = False
        self._task = None
        # We need an adapter to fetch prices and execute orders.
        # Ideally, we should reuse the same logic as endpoints.
        self.adapter = None 

    def _get_adapter(self):
        # Determine adapter based on mode (Real vs Mock)
        # Note: In real mode, we need keys. For simplicity MVP, we rely on endpoints/adapter logic
        # or we instantiate a transient adapter here.
        if settings.TRADING_MODE.upper() == "REAL":
            # For simplicity, we assume we can instantiate KiwoomRealAdapter without keys for just price checks?
            # No, we need keys for orders. 
            # We will use the same fallback logic: Try to get form DB or Env.
            # But creating a new adapter every second is expensive.
            # We should initialize it once or lazily.
            return KiwoomRealAdapter() 
        else:
            return KiwoomMockAdapter()

    async def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.adapter = self._get_adapter()
        self._task = asyncio.create_task(self._watch_loop())
        logger.info("ConditionWatcher started")

    async def stop(self):
        self.is_running = False
        if self._task:
            await self._task
        logger.info("ConditionWatcher stopped")

    async def _watch_loop(self):
        while self.is_running:
            try:
                await self._check_conditions()
            except Exception as e:
                logger.error(f"Error in watch loop: {e}")
            
            await asyncio.sleep(2) # Check every 2 seconds

    async def _check_conditions(self):
        # Create a fresh DB session for each check cycle
        db: Session = SessionLocal()
        try:
            # 1. Fetch ALL Pending conditions
            pending_orders = db.query(ConditionalOrder).filter(
                ConditionalOrder.status == ConditionStatus.PENDING
            ).all()

            if not pending_orders:
                return

            # Group by symbol to optimize API calls (if adapter supports multi-price fetch)
            # Currently KiwoomRealAdapter fetches one by one usually, but let's iterate.
            
            for cond in pending_orders:
                await self._process_condition(db, cond)

        finally:
            db.close()

    async def _process_condition(self, db: Session, cond: ConditionalOrder):
        try:
            if not self.adapter:
                 self.adapter = self._get_adapter()

            # 1. Get Current Price
            price_info = await self.adapter.get_current_price(cond.symbol)
            current_price = price_info.get("price", 0)
            
            if current_price <= 0:
                return # Invalid price, skip

            triggered = False
            
            # 2. Check Conditions
            if cond.condition_type == ConditionType.STOP_LOSS:
                if current_price <= cond.trigger_price:
                    triggered = True
                    logger.info(f"STOP LOSS Triggered for {cond.symbol}: Price {current_price} <= {cond.trigger_price}")
            
            elif cond.condition_type == ConditionType.TAKE_PROFIT:
                if current_price >= cond.trigger_price:
                    triggered = True
                    logger.info(f"TAKE PROFIT Triggered for {cond.symbol}: Price {current_price} >= {cond.trigger_price}")

            elif cond.condition_type == ConditionType.BUY_STOP:
                if current_price >= cond.trigger_price:
                    triggered = True
                    logger.info(f"BUY STOP Triggered for {cond.symbol}: Price {current_price} >= {cond.trigger_price}")
            
            elif cond.condition_type == ConditionType.BUY_LIMIT:
                if current_price <= cond.trigger_price:
                    triggered = True
                    logger.info(f"BUY LIMIT Triggered for {cond.symbol}: Price {current_price} <= {cond.trigger_price}")

            # 3. Execute Order if Triggered
            if triggered:
                # Update Status to TRIGGERED first to prevent double firing
                cond.status = ConditionStatus.TRIGGERED
                cond.triggered_at = func.now()
                db.commit()

                logger.info(f"Executing {cond.order_type} order for {cond.symbol}")
                
                # Execute Order
                exec_price = 0 if cond.price_type.lower() == "market" else cond.order_price
                
                if cond.order_type.lower() == "sell":
                    result = await self.adapter.place_sell_order(cond.symbol, exec_price, cond.quantity)
                elif cond.order_type.lower() == "buy":
                    result = await self.adapter.place_buy_order(cond.symbol, exec_price, cond.quantity)
                else:
                    result = {"status": "failed", "message": f"Unknown trigger order type: {cond.order_type}"}
                    
                    if result.get("status") == "success":
                        cond.status = ConditionStatus.COMPLETED
                        logger.info(f"Order Executed Successfully: {result}")
                    else:
                        cond.status = ConditionStatus.FAILED
                        logger.error(f"Order Execution Failed: {result}")
                        # Ideally, we might want to retry or alert user
                
                db.commit()
                
        except Exception as e:
            logger.error(f"Error processing condition {cond.id}: {e}")

# Global Instance
condition_watcher = ConditionWatcher()
