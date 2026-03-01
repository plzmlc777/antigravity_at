"""
AI Trading API endpoints.
CRUD for AI profiles + start/stop/trigger + decision history.
"""
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.user_context import UserAccountContext, get_user_context
from ..db.session import get_db
from ..models.ai_trading import AITradingProfile, AITradingDecision

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Request/Response Schemas ─────────────────────────────────

class AIProfileCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    strategy_name: str
    stock_source_mode: str = "AI_AUTO_SEARCH"
    fixed_symbols: Optional[List[Dict[str, Any]]] = None
    candidate_symbols: Optional[List[Dict[str, Any]]] = None
    search_conditions: Optional[str] = None
    param_ranges: Optional[Dict[str, Any]] = None
    fixed_params: Optional[Dict[str, Any]] = None
    backtest_days: int = 30
    backtest_interval: str = "1m"
    optimization_top_n: int = 5
    max_optimization_combos: int = 500
    approval_mode: str = "AUTO"
    account_id: Optional[int] = None
    initial_capital: float = 10_000_000
    is_paper: bool = True
    max_consecutive_losses: int = 5
    cooldown_minutes: int = 0


class AIProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    strategy_name: Optional[str] = None
    stock_source_mode: Optional[str] = None
    fixed_symbols: Optional[List[Dict[str, Any]]] = None
    candidate_symbols: Optional[List[Dict[str, Any]]] = None
    search_conditions: Optional[str] = None
    param_ranges: Optional[Dict[str, Any]] = None
    fixed_params: Optional[Dict[str, Any]] = None
    backtest_days: Optional[int] = None
    backtest_interval: Optional[str] = None
    optimization_top_n: Optional[int] = None
    max_optimization_combos: Optional[int] = None
    approval_mode: Optional[str] = None
    account_id: Optional[int] = None
    initial_capital: Optional[float] = None
    is_paper: Optional[bool] = None
    max_consecutive_losses: Optional[int] = None
    cooldown_minutes: Optional[int] = None


# ── Profile CRUD ─────────────────────────────────────────────

@router.get("/profiles")
def list_profiles(
    strategy_name: Optional[str] = None,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db),
):
    query = db.query(AITradingProfile).filter(
        AITradingProfile.user_id == ctx.user_id,
        AITradingProfile.is_active == True,
    )
    if strategy_name:
        query = query.filter(AITradingProfile.strategy_name == strategy_name)

    profiles = query.order_by(AITradingProfile.updated_at.desc()).all()

    return {
        "total": len(profiles),
        "data": [_profile_to_dict(p) for p in profiles],
    }


@router.post("/profiles")
def create_profile(
    req: AIProfileCreateRequest,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db),
):
    profile = AITradingProfile(
        id=str(uuid.uuid4()),
        user_id=ctx.user_id,
        name=req.name,
        description=req.description,
        strategy_name=req.strategy_name,
        stock_source_mode=req.stock_source_mode,
        fixed_symbols=req.fixed_symbols,
        candidate_symbols=req.candidate_symbols,
        search_conditions=req.search_conditions,
        param_ranges=req.param_ranges,
        fixed_params=req.fixed_params,
        backtest_days=req.backtest_days,
        backtest_interval=req.backtest_interval,
        optimization_top_n=req.optimization_top_n,
        max_optimization_combos=req.max_optimization_combos,
        approval_mode=req.approval_mode,
        account_id=req.account_id,
        initial_capital=req.initial_capital,
        is_paper=req.is_paper,
        max_consecutive_losses=req.max_consecutive_losses,
        cooldown_minutes=req.cooldown_minutes,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    return {
        "status": "success",
        "message": f"AI Profile '{req.name}' created",
        "data": _profile_to_dict(profile),
    }


@router.get("/profiles/{profile_id}")
def get_profile(
    profile_id: str,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db),
):
    profile = db.query(AITradingProfile).filter(
        AITradingProfile.id == profile_id,
        AITradingProfile.user_id == ctx.user_id,
        AITradingProfile.is_active == True,
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="AI Profile not found")

    return {"data": _profile_to_dict(profile)}


@router.put("/profiles/{profile_id}")
def update_profile(
    profile_id: str,
    req: AIProfileUpdateRequest,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db),
):
    profile = db.query(AITradingProfile).filter(
        AITradingProfile.id == profile_id,
        AITradingProfile.user_id == ctx.user_id,
        AITradingProfile.is_active == True,
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="AI Profile not found")
    if profile.is_running:
        raise HTTPException(status_code=400, detail="Cannot edit a running profile. Stop AI trading first.")

    update_data = req.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(profile, key, value)
    profile.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(profile)

    return {
        "status": "success",
        "message": f"AI Profile '{profile.name}' updated",
        "data": _profile_to_dict(profile),
    }


@router.delete("/profiles/{profile_id}")
def delete_profile(
    profile_id: str,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db),
):
    profile = db.query(AITradingProfile).filter(
        AITradingProfile.id == profile_id,
        AITradingProfile.user_id == ctx.user_id,
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="AI Profile not found")
    if profile.is_running:
        raise HTTPException(status_code=400, detail="Cannot delete a running profile")

    profile.is_active = False
    profile.updated_at = datetime.utcnow()
    db.commit()

    return {"status": "success", "message": f"AI Profile '{profile.name}' deleted"}


# ── AI Trading Control ───────────────────────────────────────

@router.post("/profiles/{profile_id}/start")
async def start_ai_trading(
    profile_id: str,
    ctx: UserAccountContext = Depends(get_user_context),
    db: Session = Depends(get_db),
):
    from ..services.ai_trading_service import AITradingService
    service = AITradingService.get_instance()
    result = await service.start_ai_trading(profile_id, ctx.user_id, account_ctx=ctx)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/profiles/{profile_id}/stop")
async def stop_ai_trading(
    profile_id: str,
    ctx: UserAccountContext = Depends(get_user_context),
):
    from ..services.ai_trading_service import AITradingService
    service = AITradingService.get_instance()
    result = await service.stop_ai_trading(profile_id, ctx.user_id)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/profiles/{profile_id}/trigger")
async def trigger_decision(
    profile_id: str,
    ctx: UserAccountContext = Depends(get_user_context),
):
    from ..services.ai_trading_service import AITradingService
    service = AITradingService.get_instance()
    result = await service.trigger_decision(profile_id, ctx.user_id, account_ctx=ctx)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ── Decision History ─────────────────────────────────────────

@router.get("/profiles/{profile_id}/decisions")
async def list_decisions(
    profile_id: str,
    limit: int = 20,
    ctx: UserAccountContext = Depends(get_user_context),
):
    from ..services.ai_trading_service import AITradingService
    service = AITradingService.get_instance()
    decisions = await service.get_decisions(profile_id, ctx.user_id, limit)
    return {"total": len(decisions), "data": decisions}


@router.get("/decisions/{decision_id}")
async def get_decision_detail(
    decision_id: str,
    ctx: UserAccountContext = Depends(get_user_context),
):
    from ..services.ai_trading_service import AITradingService
    service = AITradingService.get_instance()
    decision = await service.get_decision_detail(decision_id, ctx.user_id)

    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")
    return {"data": decision}


# ── Helpers ──────────────────────────────────────────────────

def _profile_to_dict(p: AITradingProfile) -> Dict:
    return {
        "id": p.id,
        "user_id": p.user_id,
        "name": p.name,
        "description": p.description,
        "strategy_name": p.strategy_name,
        "stock_source_mode": p.stock_source_mode,
        "fixed_symbols": p.fixed_symbols,
        "candidate_symbols": p.candidate_symbols,
        "search_conditions": p.search_conditions,
        "param_ranges": p.param_ranges,
        "fixed_params": p.fixed_params,
        "backtest_days": p.backtest_days,
        "backtest_interval": p.backtest_interval,
        "optimization_top_n": p.optimization_top_n,
        "max_optimization_combos": p.max_optimization_combos,
        "approval_mode": p.approval_mode,
        "account_id": p.account_id,
        "initial_capital": p.initial_capital,
        "is_paper": p.is_paper,
        "max_consecutive_losses": p.max_consecutive_losses,
        "cooldown_minutes": p.cooldown_minutes,
        "is_running": p.is_running,
        "current_session_id": p.current_session_id,
        "current_symbol": p.current_symbol,
        "cycles_completed": p.cycles_completed,
        "consecutive_losses": p.consecutive_losses,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        "last_decision_at": p.last_decision_at.isoformat() if p.last_decision_at else None,
    }
