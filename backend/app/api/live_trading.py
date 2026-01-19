from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from ..core.live_manager import live_manager

router = APIRouter()

class LiveBotStartRequest(BaseModel):
    symbol: str
    strategy_name: str = "time_momentum"
    strategy_config: Dict[str, Any] = {}
    initial_capital: float = 10000000

@router.post("/start")
async def start_live_bot(req: LiveBotStartRequest):
    """
    Start a new Live Trading Session.
    """
    try:
        config = req.dict()
        session_id = await live_manager.start_session(config)
        return {"status": "success", "session_id": session_id, "message": "Live Session Started"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/stop/{session_id}")
async def stop_live_bot(session_id: str):
    try:
        await live_manager.stop_session(session_id)
        return {"status": "success", "message": f"Session {session_id} Stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ToggleOrdersRequest(BaseModel):
    enabled: bool

@router.post("/toggle-orders/{session_id}")
async def toggle_orders(session_id: str, req: ToggleOrdersRequest):
    try:
        await live_manager.toggle_orders(session_id, req.enabled)
        return {"status": "success", "orders_enabled": req.enabled}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/liquidate/{session_id}")
async def liquidate_session(session_id: str):
    """
    Emergency: Market Sell all positions and pause trading.
    """
    try:
        await live_manager.liquidate_session(session_id)
        return {"status": "success", "message": "Liquidation order sent and trading paused."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def get_live_status():
    """
    Get status of all active Live Sessions.
    """
    return live_manager.get_status()

from fastapi import WebSocket, WebSocketDisconnect
import asyncio

@router.websocket("/ws/{session_id}")
async def websocket_live_feed(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for Real-time Tick & Candle updates.
    """
    await websocket.accept()
    
    queue = asyncio.Queue(maxsize=100)
    listeners = None
    
    try:
        # Subscribe
        listeners = await live_manager.subscribe_to_session(session_id, queue)
        
        while True:
            # Wait for data from queue
            data = await queue.get()
            
            # Send to Frontend
            await websocket.send_json(data)
            
    except WebSocketDisconnect:
        # Expected disconnect
        pass
    except Exception as e:
        print(f"WS Error: {e}")
        # Optional: Send error to client before closing?
    finally:
        # Unsubscribe
        if listeners:
            live_manager.unsubscribe_from_session(session_id, listeners)
        # await websocket.close() # Usually auto-closed by FastAPI on disconnect exception


from ..core.market_data_router import market_data_router

@router.websocket("/ws/watch/{symbol}")
async def websocket_watch_symbol(websocket: WebSocket, symbol: str):
    """
    Watch real-time ticks for a specific symbol (No Bot required).
    """
    # Connect directly to Router
    await market_data_router.connect(websocket, symbol)

