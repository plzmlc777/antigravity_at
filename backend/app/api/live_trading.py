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

@router.get("/status")
async def get_live_status():
    """
    Get status of all active Live Sessions.
    """
    return live_manager.get_status()

