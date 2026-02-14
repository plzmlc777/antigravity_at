from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import asyncio
import json
import logging

from ..db.session import get_db
from ..models.strategy_request import StrategyRequest
from ..models.user import User
from .auth import get_current_user

logger = logging.getLogger("strategy_lab")

router = APIRouter()


# ============================================================
# Pydantic Schemas
# ============================================================
class StrategyRequestCreate(BaseModel):
    name: str
    description: Optional[str] = None
    entry_type: str = "price"
    entry_condition: str
    indicators: Optional[list] = None
    entry_mode: str = "single"
    additional_entry: Optional[str] = None
    exit_condition: Optional[str] = None
    custom_parameters: Optional[list] = None
    default_overrides: Optional[dict] = None
    notes: Optional[str] = None
    status: str = "draft"


class StrategyRequestUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    entry_type: Optional[str] = None
    entry_condition: Optional[str] = None
    indicators: Optional[list] = None
    entry_mode: Optional[str] = None
    additional_entry: Optional[str] = None
    exit_condition: Optional[str] = None
    custom_parameters: Optional[list] = None
    default_overrides: Optional[dict] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    strategy_id: Optional[str] = None


class StrategyRequestOut(BaseModel):
    id: str
    user_id: int
    name: str
    strategy_id: Optional[str] = None
    description: Optional[str] = None
    entry_type: str
    entry_condition: str
    indicators: Optional[list] = None
    entry_mode: str
    additional_entry: Optional[str] = None
    exit_condition: Optional[str] = None
    custom_parameters: Optional[list] = None
    default_overrides: Optional[dict] = None
    notes: Optional[str] = None
    status: str
    implemented_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ============================================================
# Endpoints
# ============================================================
@router.get("/requests", response_model=List[StrategyRequestOut])
async def list_strategy_requests(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all strategy requests for the current user."""
    query = db.query(StrategyRequest).filter(
        StrategyRequest.user_id == current_user.id
    )
    if status:
        query = query.filter(StrategyRequest.status == status)
    return query.order_by(StrategyRequest.created_at.desc()).all()


@router.post("/requests", response_model=StrategyRequestOut)
async def create_strategy_request(
    req: StrategyRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new strategy request."""
    db_obj = StrategyRequest(
        user_id=current_user.id,
        name=req.name,
        description=req.description,
        entry_type=req.entry_type,
        entry_condition=req.entry_condition,
        indicators=req.indicators,
        entry_mode=req.entry_mode,
        additional_entry=req.additional_entry,
        exit_condition=req.exit_condition,
        custom_parameters=req.custom_parameters,
        default_overrides=req.default_overrides,
        notes=req.notes,
        status=req.status,
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


@router.get("/requests/{request_id}", response_model=StrategyRequestOut)
async def get_strategy_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a single strategy request by ID."""
    obj = db.query(StrategyRequest).filter(
        StrategyRequest.id == request_id,
        StrategyRequest.user_id == current_user.id
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Strategy request not found")
    return obj


@router.put("/requests/{request_id}", response_model=StrategyRequestOut)
async def update_strategy_request(
    request_id: str,
    updates: StrategyRequestUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a strategy request."""
    obj = db.query(StrategyRequest).filter(
        StrategyRequest.id == request_id,
        StrategyRequest.user_id == current_user.id
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Strategy request not found")

    update_data = updates.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(obj, key, value)

    obj.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/requests/{request_id}")
async def delete_strategy_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a strategy request."""
    obj = db.query(StrategyRequest).filter(
        StrategyRequest.id == request_id,
        StrategyRequest.user_id == current_user.id
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Strategy request not found")

    db.delete(obj)
    db.commit()
    return {"status": "deleted", "id": request_id}


@router.post("/requests/{request_id}/activate")
async def activate_strategy(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Activate a tested strategy — makes it visible in Profiles page."""
    from ..models.strategy_info import StrategyInfo

    request = db.query(StrategyRequest).filter(
        StrategyRequest.id == request_id,
        StrategyRequest.user_id == current_user.id
    ).first()
    if not request:
        raise HTTPException(status_code=404, detail="Strategy request not found")

    if request.status != "implemented":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot activate: status is '{request.status}', must be 'implemented'"
        )
    if not request.strategy_id:
        raise HTTPException(status_code=400, detail="No linked strategy_id")

    strategy = db.query(StrategyInfo).filter(
        StrategyInfo.id == request.strategy_id
    ).first()
    if not strategy:
        raise HTTPException(
            status_code=404,
            detail=f"Strategy '{request.strategy_id}' not found in strategy_info"
        )

    strategy.status = "active"
    request.status = "active"
    request.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(request)

    return {
        "status": "activated",
        "request_id": request_id,
        "strategy_id": request.strategy_id,
        "message": f"Strategy '{strategy.name}' is now active and visible in Profiles"
    }


# ============================================================
# AI Chat (Claude Code CLI Subprocess)
# ============================================================
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None  # Claude Code conversation ID for multi-turn


class ChatResponse(BaseModel):
    response: str
    session_id: Optional[str] = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None


@router.post("/chat", response_model=ChatResponse)
async def strategy_lab_chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Chat with Claude Code to design trading strategies.
    Uses claude CLI as a subprocess with the strategy-builder agent.
    """
    import shutil

    claude_path = shutil.which("claude")
    if not claude_path:
        raise HTTPException(
            status_code=503,
            detail="Claude CLI not found. Install Claude Code first."
        )

    # Build command
    cmd = [
        claude_path,
        "-p", request.message,
        "--output-format", "json",
        "--agent", "strategy-builder",
        "--permission-mode", "bypassPermissions",
    ]

    # Resume existing conversation for multi-turn
    if request.session_id:
        cmd.extend(["--resume", request.session_id])

    logger.info(f"[StrategyLabChat] user={current_user.id}, session={request.session_id or 'new'}, msg_len={len(request.message)}")

    import os
    env = os.environ.copy()
    # Remove PM2 IPC env vars that interfere with Claude CLI (also a Node.js process)
    for key in ["NODE_CHANNEL_FD", "NODE_CHANNEL_SERIALIZATION_MODE", "NODE_APP_INSTANCE"]:
        env.pop(key, None)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd="/home/hcpark/antigravity",
            env=env,
            start_new_session=True,
        )

        # Timeout: 300 seconds max (Claude CLI can be slow on first load)
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        except asyncio.TimeoutError:
            proc.kill()
            # Capture partial output for debugging
            logger.error(f"[StrategyLabChat] TIMEOUT. stderr might have clues.")
            return ChatResponse(
                response="",
                error="Response timed out (5min). Try a simpler question."
            )

        if proc.returncode != 0:
            err_msg = stderr.decode().strip() if stderr else "Unknown error"
            logger.error(f"[StrategyLabChat] CLI error: {err_msg}")
            return ChatResponse(response="", error=f"Claude CLI error: {err_msg[:200]}")

        # Parse JSON output
        raw = stdout.decode().strip()
        if not raw:
            return ChatResponse(response="", error="Empty response from Claude CLI")

        data = json.loads(raw)

        return ChatResponse(
            response=data.get("result", ""),
            session_id=data.get("session_id"),
            duration_ms=data.get("duration_ms"),
        )

    except json.JSONDecodeError as e:
        logger.error(f"[StrategyLabChat] JSON parse error: {e}")
        return ChatResponse(response="", error="Failed to parse Claude response")
    except Exception as e:
        logger.error(f"[StrategyLabChat] Unexpected error: {e}")
        return ChatResponse(response="", error=str(e)[:200])
