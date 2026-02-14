from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from ..db.session import get_db
from ..models.strategy_request import StrategyRequest
from ..models.user import User
from .auth import get_current_user

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
