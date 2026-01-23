from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Dict, Any, Optional
from datetime import datetime

from ..db.session import get_db
from ..models.live_trading import LiveBotSession, LiveTradeExecution
from ..models.ohlcv import OHLCV

router = APIRouter()

@router.get("/sessions", response_model=List[Dict[str, Any]])
def get_history_sessions(db: Session = Depends(get_db)):
    """
    List all recorded Live Sessions (descending start time).
    """
    sessions = db.query(LiveBotSession).order_by(desc(LiveBotSession.started_at)).all()
    
    results = []
    for s in sessions:
        results.append({
            "id": s.id,
            "symbol": s.symbol,
            "status": s.status,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "stopped_at": s.stopped_at.isoformat() if s.stopped_at else None,
            "strategy_name": s.strategy_name,
            "initial_capital": s.initial_capital,
            "current_capital": s.current_capital,
            "is_paper": s.is_paper
        })
    return results

@router.get("/sessions/{session_id}", response_model=Dict[str, Any])
def get_session_details(session_id: str, db: Session = Depends(get_db)):
    """
    Get generic details + executions + candles for replay.
    """
    session = db.query(LiveBotSession).filter(LiveBotSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    # 1. Executions
    executions = db.query(LiveTradeExecution).filter(
        LiveTradeExecution.session_id == session_id
    ).order_by(LiveTradeExecution.signal_timestamp).all()
    
    formatted_execs = []
    for ex in executions:
        formatted_execs.append({
            "id": ex.id,
            "signal_type": ex.signal_type,
            "signal_timestamp": ex.signal_timestamp.isoformat(),
            "theoretical_price": ex.theoretical_price,
            "requested_quantity": ex.requested_quantity,
            "status": ex.status,
            "executed_price": ex.executed_price,
            "filled_quantity": ex.filled_quantity,
            "slippage_percent": ex.slippage_percent
        })
        
    # 2. Candles
    # Fetch 1m candles for the session duration
    start = session.started_at
    end = session.stopped_at or datetime.now()
    
    candles_query = db.query(OHLCV).filter(
        OHLCV.symbol == session.symbol,
        OHLCV.timestamp >= start,
        OHLCV.timestamp <= end,
        OHLCV.time_frame == "1m"
    ).order_by(OHLCV.timestamp.asc())
    
    candles = candles_query.all()
    
    formatted_candles = []
    for c in candles:
        formatted_candles.append({
            "timestamp": c.timestamp.isoformat(),
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume
        })
        
    return {
        "session": {
            "id": session.id,
            "symbol": session.symbol,
            "status": session.status,
            "started_at": session.started_at.isoformat(),
            "stopped_at": session.stopped_at.isoformat() if session.stopped_at else None,
            "config": session.strategy_config,
            "is_paper": session.is_paper
        },
        "executions": formatted_execs,
        "candles": formatted_candles
    }
