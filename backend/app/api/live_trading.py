from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from ..core.live_manager import live_manager
from ..db.session import get_db
from sqlalchemy.orm import Session
from fastapi import Depends
from ..models.live_trading import LiveBotSession, LiveRealizedTrade, LiveEquitySnapshot
from ..services.stats_service import StatsService

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


@router.get("/sessions/{session_id}/stats")
async def get_session_stats(session_id: str, db: Session = Depends(get_db)):
    """
    Get comprehensive performance stats for a session using StatsService.
    """
    session = db.query(LiveBotSession).filter(LiveBotSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    # Fetch Trades and Equity Curve for Calculation
    trades = db.query(LiveRealizedTrade).filter(
        LiveRealizedTrade.session_id == session_id
    ).all()
    
    equity_curve = db.query(LiveEquitySnapshot).filter(
        LiveEquitySnapshot.session_id == session_id
    ).order_by(LiveEquitySnapshot.timestamp.asc()).all()
    
    # Calculate detailed stats
    stats = StatsService.calculate_detailed_stats(
        trades, 
        equity_curve, 
        session.started_at,
        initial_capital=session.initial_capital
    )
    
    # Merge with basic session info
    stats.update({
        "status": session.status,
        "started_at": session.started_at,
        "stopped_at": session.stopped_at,
        "current_capital": session.current_capital # Keep for header reference
    })
    
    return stats

@router.get("/sessions/{session_id}/equity-curve")
async def get_session_equity_curve(session_id: str, db: Session = Depends(get_db)):
    """
    Get historical equity snapshots for charting.
    """
    snapshots = db.query(LiveEquitySnapshot).filter(
        LiveEquitySnapshot.session_id == session_id
    ).order_by(LiveEquitySnapshot.timestamp.asc()).all()
    
    return [
        {
            "timestamp": s.timestamp.isoformat(),
            "equity": s.equity,
            "cash": s.cash,
            "holdings_value": s.holdings_value,
            "drawdown": s.drawdown
        } for s in snapshots
    ]

@router.get("/sessions/{session_id}/trades")
async def get_session_realized_trades(session_id: str, db: Session = Depends(get_db)):
    """
    Get realized (round-trip) trades for a session.
    """
    trades = db.query(LiveRealizedTrade).filter(
        LiveRealizedTrade.session_id == session_id
    ).order_by(LiveRealizedTrade.exit_time.desc()).all()
    
    return [
        {
            "id": t.id,
            "symbol": t.symbol,
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "entry_time": t.entry_time.isoformat(),
            "exit_time": t.exit_time.isoformat(),
            "quantity": t.quantity,
            "pnl": t.pnl,
            "pnl_percent": t.pnl_percent,
            "holding_seconds": t.holding_seconds
        } for t in trades
    ]

from ..core.market_data_router import market_data_router

@router.websocket("/ws/watch/{symbol}")
async def websocket_watch_symbol(websocket: WebSocket, symbol: str):
    """
    Watch real-time ticks for a specific symbol (No Bot required).
    """
    # Connect directly to Router
    await market_data_router.connect(websocket, symbol)

