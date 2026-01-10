from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from ..core.bot_manager import bot_manager

router = APIRouter()

class LiveBotStartRequest(BaseModel):
    symbol: str
    strategy: str # 'time_momentum' or 'rsi'
    strategy_config: Dict[str, Any] = {}
    interval: int = 60
    amount: float = 1000000

@router.post("/start")
async def start_live_bot(req: LiveBotStartRequest):
    """
    Start a new Live Trading Session.
    """
    try:
        # Pydantic .dict()
        config = req.dict()
        session_id = bot_manager.start_live_session(config)
        return {"status": "success", "session_id": session_id, "message": "Live Bot Started"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/stop/{session_id}")
async def stop_live_bot(session_id: str):
    try:
        bot_manager.stop_live_session(session_id)
        return {"status": "success", "message": f"Session {session_id} Stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/pause/{session_id}")
async def pause_live_bot(session_id: str):
    try:
        bot_manager.pause_live_session(session_id)
        return {"status": "success", "message": f"Session {session_id} Paused"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/resume/{session_id}")
async def resume_live_bot(session_id: str):
    try:
        bot_manager.resume_live_session(session_id)
        return {"status": "success", "message": f"Session {session_id} Resumed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def get_live_status():
    """
    Get status of all active/paused Live Bots.
    """
    return bot_manager.get_live_status()
